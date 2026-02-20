"""
Views for Quantum Chess Django application.

This module contains the views for handling game logic and rendering templates.
"""

import json
import chess
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator

from .models import Game, Move, QuantumPiece as GameQuantumPiece
from .quantum.quant import QuantumPiece as QPiece, QuantumGame


def index(request):
    """
    Home page view - displays the main landing page.
    """
    return render(request, 'quantum_chess/index.html')


def game(request, game_id):
    """
    Game view - displays the chess board for a specific game.
    """
    game_obj = get_object_or_404(Game, id=game_id)
    
    # Update status from 'waiting' to 'active' when player accesses the game
    if game_obj.status == 'waiting':
        game_obj.status = 'active'
        game_obj.save()
    
    return render(request, 'quantum_chess/game.html', {
        'game': game_obj,
    })



def new_game(request):
    """
    Create a new quantum chess game and redirect to the game page.
    """
    game_obj = Game.objects.create(
        status='waiting',
        current_turn=True,
        fen_position=chess.STARTING_FEN,
        quantum_mode=False,
    )
    # Redirect to the game page with the new game ID
    return redirect('quantum_chess:game', game_id=game_obj.id)


@csrf_exempt
@require_http_methods(["POST"])
def make_move(request):
    """
    API endpoint to make a move in the quantum chess game.
    """
    try:
        data = json.loads(request.body)
        game_id = data.get('game_id')
        from_square = data.get('from_square')
        to_square = data.get('to_square')
        promotion = data.get('promotion')
        quantum_mode = data.get('quantum_mode', False)
        
        game_obj = get_object_or_404(Game, id=game_id)
        
        # Handle quantum mode toggle without a move
        if from_square is None and to_square is None:
            game_obj.quantum_mode = quantum_mode
            game_obj.save()
            return JsonResponse({
                'success': True,
                'quantum_mode': game_obj.quantum_mode,
                'message': 'Quantum mode updated'
            })
        
        # Parse chess squares
        from_sq = chess.parse_square(from_square) if isinstance(from_square, str) else from_square
        to_sq = chess.parse_square(to_square) if isinstance(to_square, str) else to_square
        
        # Create chess board from FEN
        board = chess.Board(fen=game_obj.fen_position)
        
        # Debug logging
        print(f"DEBUG make_move: game_id={game_id}, from={from_square}({from_sq}), to={to_square}({to_sq})")
        print(f"DEBUG board FEN: {board.fen()}")
        print(f"DEBUG board turn: {'white' if board.turn == chess.WHITE else 'black'}")
        print(f"DEBUG game current_turn: {game_obj.current_turn}")
        print(f"DEBUG legal moves count: {len(list(board.legal_moves))}")
        
        # Create move
        move = chess.Move(from_sq, to_sq)
        if promotion:
            move.promotion = chess.Piece.from_symbol(promotion).piece_type
        
        # Check if move is legal
        if move not in board.legal_moves:
            print(f"DEBUG: Move {move} not in legal moves. Legal moves: {list(board.legal_moves)[:10]}...")
            return JsonResponse({
                'success': False,
                'error': 'Illegal move',
                'debug': {
                    'fen': board.fen(),
                    'turn': 'white' if board.turn == chess.WHITE else 'black',
                    'requested_move': f"{from_square}->{to_square}",
                }
            }, status=400)

        
        # Get quantum pieces data
        quantum_pieces_data = game_obj.quantum_pieces if game_obj.quantum_pieces else []
        from_square_name = chess.square_name(from_sq)
        to_square_name = chess.square_name(to_sq)
        
        # Get the piece being moved
        piece = board.piece_at(from_sq)
        moved_piece_symbol = piece.symbol() if piece else None

        
        # Check if we're capturing a quantum piece at the destination
        # If so, we need to collapse that quantum piece from ALL its positions
        captured_quantum_index = None
        captured_quantum_positions = []
        
        for i, qp in enumerate(quantum_pieces_data):
            for state_id, state_data in qp.get('qnum', {}).items():
                if state_data[0] == to_square_name:
                    # We're capturing a quantum piece!
                    captured_quantum_index = i
                    # Get all positions of this quantum piece
                    for all_state_id, all_state_data in qp.get('qnum', {}).items():
                        captured_quantum_positions.append(all_state_data[0])
                    break
            if captured_quantum_index is not None:
                break
        
        # Check if the piece being moved is in quantum state (moving from superposition)
        moving_quantum_index = None
        moving_quantum_other_positions = []
        
        for i, qp in enumerate(quantum_pieces_data):
            for state_id, state_data in qp.get('qnum', {}).items():
                if state_data[0] == from_square_name:
                    moving_quantum_index = i
                    # Find all other positions for this quantum piece
                    for other_state_id, other_state_data in qp.get('qnum', {}).items():
                        if other_state_id != state_id:
                            moving_quantum_other_positions.append(other_state_data[0])
                    break
            if moving_quantum_index is not None:
                break
        
        # Make the move
        san = board.san(move)
        board.push(move)
        
        # If we captured a quantum piece, the capture reveals its actual position
        # So the piece collapses to 100% at the captured position, other positions are removed
        if captured_quantum_index is not None and captured_quantum_positions:
            print(f"DEBUG: Capturing quantum piece at {to_square_name}")
            print(f"DEBUG: Quantum piece was at positions: {captured_quantum_positions}")
            
            # Remove piece from the board at capture position
            board.remove_piece_at(to_sq)
            print(f"DEBUG: Removed piece from capture position {to_square_name}")
            
            # Capturing a quantum piece "measures" it - we now know it was at the captured position
            # So collapse to 100% at the captured position, remove all other positions
            # The piece becomes a classical piece at the capture destination
            
            # Get the piece type from quantum piece data
            captured_piece_type = quantum_pieces_data[captured_quantum_index].get('piece')
            
            # Remove the quantum piece from quantum_pieces_data (it becomes classical)
            quantum_pieces_data.pop(captured_quantum_index)
            print(f"DEBUG: Removed quantum piece from data list (collapsed to captured position)")
            
            # Place the captured piece as a classical piece at the destination
            if captured_piece_type:
                board.set_piece_at(to_sq, chess.Piece.from_symbol(captured_piece_type))
                print(f"DEBUG: Placed captured piece {captured_piece_type} at {to_square_name} as classical piece")
            
            # Also place the capturing piece if there is one
            if moved_piece_symbol:
                # The capturing piece goes to the captured position
                board.set_piece_at(to_sq, chess.Piece.from_symbol(moved_piece_symbol))
                print(f"DEBUG: Placed capturing piece {moved_piece_symbol} at {to_square_name}")
        
        # If this was a quantum piece being moved, collapse its other superpositions
        if moving_quantum_index is not None and moving_quantum_other_positions:
            print(f"DEBUG: Collapsing moved quantum piece from {from_square_name} to {to_square_name}")
            print(f"DEBUG: Removing piece from other positions: {moving_quantum_other_positions}")
            for other_pos in moving_quantum_other_positions:
                other_sq = chess.parse_square(other_pos)
                # Remove the piece from the other superposition position
                board.remove_piece_at(other_sq)
            
            # Update the quantum piece state - move it to the new position
            # Adjust index if we removed a piece before it
            adjusted_index = moving_quantum_index
            if captured_quantum_index is not None and captured_quantum_index < moving_quantum_index:
                adjusted_index = moving_quantum_index - 1
            
            if adjusted_index < len(quantum_pieces_data):
                quantum_pieces_data[adjusted_index]['qnum'] = {
                    '0': [to_square_name, 1.0]  # Collapsed to 100% probability at new position
                }
                
                # Remove entanglement since piece is now measured/collapsed
                quantum_pieces_data[adjusted_index]['entangled'] = []
        
        # Update game status based on board state
        if board.is_checkmate():
            game_obj.status = 'checkmate'
        elif board.is_stalemate():
            game_obj.status = 'stalemate'
        elif board.is_insufficient_material():
            game_obj.status = 'draw'
        elif board.is_fivefold_repetition():
            game_obj.status = 'draw'
        elif board.is_seventyfive_moves():
            game_obj.status = 'draw'
        elif board.is_variant_draw():
            game_obj.status = 'draw'
        else:
            game_obj.status = 'active'
        
        # Update game
        game_obj.fen_position = board.fen()
        game_obj.current_turn = not game_obj.current_turn
        game_obj.quantum_mode = quantum_mode
        game_obj.quantum_pieces = quantum_pieces_data
        game_obj.save()


        
        # Record move
        move_count = Move.objects.filter(game=game_obj).count()
        Move.objects.create(
            game=game_obj,
            move_number=move_count // 2 + 1,
            is_white_move=board.turn == chess.BLACK,  # Turn changed after push
            move_type='normal',
            from_square=from_sq,
            to_square=to_sq,
            promotion=promotion,
            san=san,
            fen_after=board.fen()
        )
        
        return JsonResponse({
            'success': True,
            'fen': board.fen(),
            'san': san,
            'turn': 'white' if board.turn == chess.WHITE else 'black',
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def quantum_split(request):
    """
    API endpoint to perform a quantum split move.
    Splits a piece into two positions in superposition.
    """
    try:
        data = json.loads(request.body)
        game_id = data.get('game_id')
        from_square = data.get('from_square')
        to_square1 = data.get('to_square1')
        to_square2 = data.get('to_square2')
        
        game_obj = get_object_or_404(Game, id=game_id)
        
        # Parse chess squares
        from_sq = chess.parse_square(from_square) if isinstance(from_square, str) else from_square
        to_sq1 = chess.parse_square(to_square1) if isinstance(to_square1, str) else to_square1
        to_sq2 = chess.parse_square(to_square2) if isinstance(to_square2, str) else to_square2
        
        # Get or create quantum game state
        quantum_pieces_data = game_obj.quantum_pieces if game_obj.quantum_pieces else []
        
        # Create a new QuantumGame instance
        quantum_game = QuantumGame()
        quantum_game.quantum_mode = True
        
        # Load existing quantum pieces if any
        for qp_data in quantum_pieces_data:
            qp = QPiece(qp_data.get('position', 'a1'), qp_data.get('piece'))
            qp.qnum = qp_data.get('qnum', {'0': [qp_data.get('position', 'a1'), 1]})
            quantum_game.quantum_pieces.append(qp)
        
        # Find or create the quantum piece at from_square
        from_square_name = chess.square_name(from_sq)
        
        # Find the piece at the from square
        board = chess.Board(fen=game_obj.fen_position)
        piece = board.piece_at(from_sq)
        
        if not piece:
            return JsonResponse({
                'success': False,
                'error': 'No piece at the source square'
            }, status=400)
        
        # Validate that target squares are legal moves for this piece
        # Create a temporary board to check legal moves
        temp_board = chess.Board(fen=game_obj.fen_position)
        legal_moves = [move for move in temp_board.legal_moves if move.from_square == from_sq]
        legal_targets = {move.to_square for move in legal_moves}
        
        if to_sq1 not in legal_targets:
            return JsonResponse({
                'success': False,
                'error': f'Illegal split: {to_square1} is not a valid move for this piece'
            }, status=400)
        
        if to_sq2 not in legal_targets:
            return JsonResponse({
                'success': False,
                'error': f'Illegal split: {to_square2} is not a valid move for this piece'
            }, status=400)
        
        # Rule: It is illegal to capture on split - target squares must be empty
        if board.piece_at(to_sq1):
            return JsonResponse({
                'success': False,
                'error': f'Illegal split: {to_square1} is occupied. Capturing is not allowed during quantum split'
            }, status=400)
        
        if board.piece_at(to_sq2):
            return JsonResponse({
                'success': False,
                'error': f'Illegal split: {to_square2} is occupied. Capturing is not allowed during quantum split'
            }, status=400)
        
        # Check if piece already exists in quantum state


        existing_qp = None
        existing_state = None
        for qp in quantum_game.quantum_pieces:
            for state_id, state_data in qp.qnum.items():
                if state_data[0] == from_square_name:
                    existing_qp = qp
                    existing_state = state_id
                    break
            if existing_qp:
                break
        
        if existing_qp and existing_state:
            # Split existing quantum piece
            existing_qp.split(existing_state, chess.square_name(to_sq1), chess.square_name(to_sq2))
        else:
            # Create new quantum piece and split it
            qp = quantum_game.add_quantum_piece(from_square_name, piece.symbol())
            qp.split('0', chess.square_name(to_sq1), chess.square_name(to_sq2))
        
        # Save quantum pieces state
        quantum_pieces_data = []
        for qp in quantum_game.quantum_pieces:
            quantum_pieces_data.append({
                'piece': str(qp.piece),
                'qnum': qp.qnum,
                'entangled': [[str(e[0].piece) if e[0] else None, e[1], e[2]] for e in qp.ent]
            })
        
        game_obj.quantum_pieces = quantum_pieces_data
        game_obj.quantum_mode = True
        
        # Update the board FEN to remove the piece from original position
        board.remove_piece_at(from_sq)
        
        # Add the piece to BOTH target positions so either can be moved
        # The piece is in quantum superposition at both locations
        board.set_piece_at(to_sq1, piece)
        board.set_piece_at(to_sq2, piece)
        
        # Switch turn in the FEN as well so chess.js knows whose turn it is
        board.turn = not board.turn
        game_obj.fen_position = board.fen()


        
        # Switch turn after quantum split
        game_obj.current_turn = not game_obj.current_turn
        
        # Update game status
        if board.is_checkmate():
            game_obj.status = 'checkmate'
        elif board.is_stalemate():
            game_obj.status = 'stalemate'
        elif board.is_insufficient_material():
            game_obj.status = 'draw'
        else:
            game_obj.status = 'active'
        
        game_obj.save()

        # Record the split move

        move_count = Move.objects.filter(game=game_obj).count()
        Move.objects.create(
            game=game_obj,
            move_number=move_count // 2 + 1,
            is_white_move=piece.color == chess.WHITE,
            move_type='split',
            from_square=from_sq,
            to_square=to_sq1,  # Store first target
            promotion=None,
            san=f'Split: {from_square}→{to_square1}/{to_square2}',
            fen_after=game_obj.fen_position
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Quantum split performed',
            'from_square': from_square,
            'to_square1': to_square1,
            'to_square2': to_square2,
            'fen': game_obj.fen_position,
            'quantum_pieces': quantum_pieces_data,
            'turn': 'white' if game_obj.current_turn else 'black',
        })


        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def toggle_quantum_mode(request):
    """
    API endpoint to toggle quantum mode for a game.
    """
    try:
        data = json.loads(request.body)
        game_id = data.get('game_id')
        quantum_mode = data.get('quantum_mode', False)
        
        game_obj = get_object_or_404(Game, id=game_id)
        game_obj.quantum_mode = quantum_mode
        game_obj.save()
        
        return JsonResponse({
            'success': True,
            'quantum_mode': game_obj.quantum_mode,
            'message': 'Quantum mode ' + ('enabled' if quantum_mode else 'disabled')
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def quantum_entangle(request):
    """
    API endpoint to perform a quantum entanglement.
    """
    try:
        data = json.loads(request.body)
        game_id = data.get('game_id')
        
        game_obj = get_object_or_404(Game, id=game_id)
        
        return JsonResponse({
            'success': True,
            'message': 'Quantum entanglement performed',
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def measure_piece(request):
    """
    API endpoint to measure a quantum piece.
    """
    try:
        data = json.loads(request.body)
        game_id = data.get('game_id')
        square = data.get('square')
        
        game_obj = get_object_or_404(Game, id=game_id)
        
        # Get or create quantum game state
        quantum_pieces_data = game_obj.quantum_pieces if game_obj.quantum_pieces else []
        
        # Create a new QuantumGame instance
        quantum_game = QuantumGame()
        quantum_game.quantum_mode = True
        
        # Load existing quantum pieces
        for qp_data in quantum_pieces_data:
            qp = QPiece(qp_data.get('position', 'a1'), qp_data.get('piece'))
            qp.qnum = qp_data.get('qnum', {'0': [qp_data.get('position', 'a1'), 1]})
            quantum_game.quantum_pieces.append(qp)
        
        # Measure the piece
        result = quantum_game.measure_piece(square)
        
        if result:
            final_pos, prob = result
            
            # Update the board - place piece at measured position
            board = chess.Board(fen=game_obj.fen_position)
            
            # Find the piece type from quantum pieces
            measured_piece = None
            for qp in quantum_game.quantum_pieces:
                for state_id, state_data in qp.qnum.items():
                    if state_data[0] == square:
                        measured_piece = qp.piece
                        break
                if measured_piece:
                    break
            
            # Remove piece from all quantum positions and place at final position
            if measured_piece:
                # Clear all quantum positions for this piece
                new_quantum_pieces = []
                for qp in quantum_game.quantum_pieces:
                    # Check if this is the measured piece
                    is_measured = False
                    for state_id, state_data in qp.qnum.items():
                        if state_data[0] == square:
                            is_measured = True
                            break
                    
                    if not is_measured:
                        # Keep other quantum pieces
                        new_quantum_pieces.append({
                            'piece': str(qp.piece),
                            'qnum': qp.qnum,
                            'entangled': [[str(e[0].piece) if e[0] else None, e[1], e[2]] for e in qp.ent]
                        })
                
                game_obj.quantum_pieces = new_quantum_pieces
            
            # Save updated game state
            game_obj.fen_position = board.fen()
            game_obj.save()
            
            return JsonResponse({
                'success': True,
                'message': f'Piece at {square} measured and collapsed to {final_pos}',
                'final_position': final_pos,
                'probability': prob,
                'fen': game_obj.fen_position,
                'quantum_pieces': game_obj.quantum_pieces
            })
        
        return JsonResponse({
            'success': False,
            'error': f'No quantum piece found at {square}'
        }, status=400)

        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def get_game_state(request, game_id):
    """
    API endpoint to get the current game state.
    """
    game_obj = get_object_or_404(Game, id=game_id)
    
    # Get all moves
    moves = Move.objects.filter(game=game_obj).order_by('move_number', 'is_white_move')
    move_list = []
    for m in moves:
        move_list.append({
            'number': m.move_number,
            'is_white': m.is_white_move,
            'san': m.san,
            'type': m.move_type,
        })
    
    return JsonResponse({
        'game_id': game_obj.id,
        'fen': game_obj.fen_position,
        'turn': 'white' if game_obj.current_turn else 'black',
        'quantum_mode': game_obj.quantum_mode,
        'status': game_obj.status,
        'moves': move_list,
        'quantum_pieces': game_obj.quantum_pieces if game_obj.quantum_pieces else [],
    })



def game_list(request):
    """
    View to list all games.
    """
    games = Game.objects.all()[:20]
    return render(request, 'quantum_chess/game_list.html', {
        'games': games,
    })
