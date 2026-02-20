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
        
        # Create move
        move = chess.Move(from_sq, to_sq)
        if promotion:
            move.promotion = chess.Piece.from_symbol(promotion).piece_type
        
        # Check if move is legal
        if move not in board.legal_moves:
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
        captured_quantum_index = None
        captured_quantum_positions = []
        
        for i, qp in enumerate(quantum_pieces_data):
            for state_id, state_data in qp.get('qnum', {}).items():
                if state_data[0] == to_square_name:
                    captured_quantum_index = i
                    for all_state_id, all_state_data in qp.get('qnum', {}).items():
                        captured_quantum_positions.append(all_state_data[0])
                    break
            if captured_quantum_index is not None:
                break
        
        # Make the move
        san = board.san(move)
        board.push(move)
        
        # If we captured a quantum piece, we need to MEASURE it (collapse superposition)
        # According to Game Rule.md: "A piece is captured" triggers measurement
        # The piece randomly collapses to one of its possible positions
        if captured_quantum_index is not None and captured_quantum_positions:
            # Get the quantum piece data to measure
            captured_qp_data = quantum_pieces_data[captured_quantum_index]
            captured_piece_type = captured_qp_data.get('piece')
            
            # Create a temporary quantum piece to measure
            temp_qp = QPiece(captured_qp_data.get('position', 'a1'), captured_piece_type)
            temp_qp.qnum = captured_qp_data.get('qnum', {'0': [captured_qp_data.get('position', 'a1'), 1]})
            
            # Measure the quantum piece - this collapses it to a random position
            measured_pos, prob = temp_qp.measure()
            
            print(f"DEBUG: Quantum piece measured. Collapsed to {measured_pos} with probability {prob}")
            
            # Remove the quantum piece from the list (it has been measured)
            quantum_pieces_data.pop(captured_quantum_index)
            
            # Check if the piece collapsed to the capture square (successful capture)
            if measured_pos == to_square_name:
                # Successful capture - piece was at the capture location
                if captured_piece_type:
                    board.set_piece_at(to_sq, chess.Piece.from_symbol(captured_piece_type))
                if moved_piece_symbol:
                    board.set_piece_at(to_sq, chess.Piece.from_symbol(moved_piece_symbol))
            else:
                # Piece collapsed to a different location - capture failed
                # The moving piece now occupies the capture square (empty)
                if moved_piece_symbol:
                    board.set_piece_at(to_sq, chess.Piece.from_symbol(moved_piece_symbol))
                # The captured piece (now classical) is at the measured position
                if captured_piece_type and measured_pos:
                    measured_sq = chess.parse_square(measured_pos)
                    board.set_piece_at(measured_sq, chess.Piece.from_symbol(captured_piece_type))
                
                print(f"DEBUG: Capture failed! Piece was at {measured_pos}, not {to_square_name}")
        
        # Update game status based on board state (with quantum consideration)
        game_obj.status = update_game_status(board, game_obj.quantum_pieces)
        
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
            is_white_move=board.turn == chess.BLACK,
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


def update_game_status(board, quantum_pieces):
    """
    Update game status considering quantum rules.
    According to Game Rule.md:
    - A king in superposition can be in two squares
    - A king is in check if ANY of its possible squares is attacked
    - Checkmate happens when ALL superposed positions of the king cannot escape check
    """
    # Get current turn's color
    turn_color = board.turn
    
    # Find the king
    king_square = None
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece and piece.piece_type == chess.KING and piece.color == turn_color:
            king_square = sq
            break
    
    if not king_square:
        return 'active'  # King not found, shouldn't happen
    
    # Check if king is in superposition
    is_quantum_king = False
    king_positions = [chess.square_name(king_square)]
    
    if quantum_pieces:
        for qp in quantum_pieces:
            piece_symbol = qp.get('piece', '')
            if 'K' in piece_symbol:  # King
                is_quantum_king = True
                for state_id, state_data in qp.get('qnum', {}).items():
                    if state_data[0]:
                        king_positions.append(state_data[0])
    
    # Check if ANY king position is in check
    in_check = False
    for pos in king_positions:
        sq = chess.parse_square(pos)
        if board.is_attacked_by(not turn_color, sq):
            in_check = True
            break
    
    if not in_check:
        return 'active'
    
    # Check if checkmate (all positions result in checkmate)
    can_escape = False
    for pos in king_positions:
        sq = chess.parse_square(pos)
        # Generate all legal moves from this position
        temp_board = chess.Board(fen=board.fen())
        temp_board.turn = turn_color
        
        # Try all possible escape moves
        for move in temp_board.legal_moves:
            test_board = chess.Board(fen=temp_board.fen())
            test_board.push(move)
            new_king_sq = move.to_square
            
            # Check if this move gets the king out of check
            if not test_board.is_attacked_by(not turn_color, new_king_sq):
                can_escape = True
                break
        
        if can_escape:
            break
    
    if not can_escape:
        return 'checkmate'
    
    return 'active'


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
            existing_qp.split(existing_state, chess.square_name(to_sq1), chess.square_name(to_sq2))
        else:
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
        board.set_piece_at(to_sq1, piece)
        board.set_piece_at(to_sq2, piece)
        
        # Switch turn in the FEN
        board.turn = not board.turn
        game_obj.fen_position = board.fen()
        
        # Switch turn after quantum split
        game_obj.current_turn = not game_obj.current_turn
        
        # Update game status
        game_obj.status = update_game_status(board, quantum_pieces_data)
        
        game_obj.save()

        # Record the split move
        move_count = Move.objects.filter(game=game_obj).count()
        Move.objects.create(
            game=game_obj,
            move_number=move_count // 2 + 1,
            is_white_move=piece.color == chess.WHITE,
            move_type='split',
            from_square=from_sq,
            to_square=to_sq1,
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
    Called when a piece moves through an occupied square.
    Per Game Rule.md: Entanglement happens when a piece moves through (not stops on) 
    a square occupied by another piece.
    """
    try:
        data = json.loads(request.body)
        game_id = data.get('game_id')
        from_square = data.get('from_square')
        to_square = data.get('to_square')
        through_square = data.get('through_square')
        
        game_obj = get_object_or_404(Game, id=game_id)
        
        # Get quantum pieces data
        quantum_pieces_data = game_obj.quantum_pieces if game_obj.quantum_pieces else []
        
        # Create a new QuantumGame instance
        quantum_game = QuantumGame()
        quantum_game.quantum_mode = True
        
        # Load existing quantum pieces
        for qp_data in quantum_pieces_data:
            qp = QPiece(qp_data.get('position', 'a1'), qp_data.get('piece'))
            qp.qnum = qp_data.get('qnum', {'0': [qp_data.get('position', 'a1'), 1]})
            quantum_game.quantum_pieces.append(qp)
        
        # Parse squares
        from_sq = chess.parse_square(from_square) if isinstance(from_square, str) else from_square
        to_sq = chess.parse_square(to_square) if isinstance(to_square, str) else to_square
        through_sq = chess.parse_square(through_square) if isinstance(through_square, str) else through_square
        
        from_square_name = chess.square_name(from_sq)
        to_square_name = chess.square_name(to_sq)
        through_square_name = chess.square_name(through_sq)
        
        # Get the moving piece
        board = chess.Board(fen=game_obj.fen_position)
        moving_piece = board.piece_at(from_sq)
        
        if not moving_piece:
            return JsonResponse({
                'success': False,
                'error': 'No piece at the source square'
            }, status=400)
        
        # Check if the through square has a quantum piece
        blocking_quantum = None
        blocking_state = None
        for qp in quantum_game.quantum_pieces:
            for state_id, state_data in qp.qnum.items():
                if state_data[0] == through_square_name:
                    blocking_quantum = qp
                    blocking_state = state_id
                    break
            if blocking_quantum:
                break
        
        # Check classical pieces at the through square
        blocking_piece = board.piece_at(through_sq)
        
        if blocking_quantum:
            # Entangle with quantum piece
            moving_quantum = None
            for qp in quantum_game.quantum_pieces:
                for state_id, state_data in qp.qnum.items():
                    if state_data[0] == from_square_name:
                        moving_quantum = qp
                        break
                if moving_quantum:
                    break
            
            if moving_quantum:
                # Both are quantum - entangle using oneblock
                moving_quantum.entangle_oneblock('0', to_square_name, blocking_quantum, blocking_state)
            else:
                # Create new quantum piece from moving piece and entangle
                moving_quantum = quantum_game.add_quantum_piece(from_square_name, moving_piece.symbol())
                moving_quantum.entangle_oneblock('0', to_square_name, blocking_quantum, blocking_state)
        
        # Save quantum pieces state
        quantum_pieces_data = []
        for qp in quantum_game.quantum_pieces:
            quantum_pieces_data.append({
                'piece': str(qp.piece),
                'qnum': qp.qnum,
                'entangled': [[str(e[0].piece) if e[0] else None, e[1], e[2]] for e in qp.ent]
            })
        
        game_obj.quantum_pieces = quantum_pieces_data
        game_obj.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Quantum entanglement performed',
            'quantum_pieces': quantum_pieces_data
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
    Per Game Rule.md: Measurement collapses superposition/entanglement to a definite state.
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
                new_quantum_pieces = []
                for qp in quantum_game.quantum_pieces:
                    is_measured = False
                    for state_id, state_data in qp.qnum.items():
                        if state_data[0] == square:
                            is_measured = True
                            break
                    
                    if not is_measured:
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


@csrf_exempt
@require_http_methods(["POST"])
def undo_move(request):
    """
    API endpoint to undo the last move.
    Restores the game to the previous FEN position.
    """
    try:
        data = json.loads(request.body)
        game_id = data.get('game_id')
        
        game_obj = get_object_or_404(Game, id=game_id)
        
        # Get all moves for this game
        moves = Move.objects.filter(game=game_obj).order_by('-id')
        
        if not moves.exists():
            return JsonResponse({
                'success': False,
                'error': 'No moves to undo'
            }, status=400)
        
        # Get the last move
        last_move = moves.first()
        
        # Delete the last move
        last_move.delete()
        
        # If there are more moves, restore to the previous position
        if moves.count() > 0:
            previous_move = moves.order_by('-id').first()
            game_obj.fen_position = previous_move.fen_after
        else:
            # No more moves, restore to starting position
            game_obj.fen_position = chess.STARTING_FEN
        
        # Toggle turn back
        game_obj.current_turn = not game_obj.current_turn
        
        # Reset status to active
        game_obj.status = 'active'
        
        game_obj.save()
        
        return JsonResponse({
            'success': True,
            'fen': game_obj.fen_position,
            'turn': 'white' if game_obj.current_turn else 'black',
            'message': 'Move undone successfully'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
