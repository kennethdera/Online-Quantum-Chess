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
                'error': 'Illegal move'
            }, status=400)
        
        # Make the move
        san = board.san(move)
        board.push(move)
        
        # Update game
        game_obj.fen_position = board.fen()
        game_obj.current_turn = not game_obj.current_turn
        game_obj.quantum_mode = quantum_mode
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
        # and add it to the quantum superposition positions
        board.remove_piece_at(from_sq)
        game_obj.fen_position = board.fen()
        
        # Switch turn after quantum split
        game_obj.current_turn = not game_obj.current_turn
        
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
    })


def game_list(request):
    """
    View to list all games.
    """
    games = Game.objects.all()[:20]
    return render(request, 'quantum_chess/game_list.html', {
        'games': games,
    })
