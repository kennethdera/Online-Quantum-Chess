"""
Views for Quantum Chess Django application.
This module contains the views for handling game logic and rendering templates.
Measurement Logic Flow (per Game Rule/measuring.txt):
- STEP 0: Trigger - Is a superposed or entangled piece involved?
- STEP 1: Identify Quantum State Type - CASE A/B/C
- SPECIAL: Measurement During Capture
"""

import json
import chess
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import Game, Move, QuantumPiece as GameQuantumPiece
from .quantum.quant import QuantumPiece as QPiece, QuantumGame


def index(request):
    return render(request, 'quantum_chess/index.html')


def game(request, game_id):
    game_obj = get_object_or_404(Game, id=game_id)
    if game_obj.status == 'waiting':
        game_obj.status = 'active'
        game_obj.save()
    return render(request, 'quantum_chess/game.html', {'game': game_obj})


def new_game(request):
    game_obj = Game.objects.create(
        status='waiting',
        current_turn=True,
        fen_position=chess.STARTING_FEN,
        quantum_mode=False,
    )
    return redirect('quantum_chess:game', game_id=game_obj.id)


@csrf_exempt
@require_http_methods(["POST"])
def make_move(request):
    """Make move with proper measurement logic per Game Rule/measuring.txt"""
    try:
        data = json.loads(request.body)
        game_id = data.get('game_id')
        from_square = data.get('from_square')
        to_square = data.get('to_square')
        promotion = data.get('promotion')
        quantum_mode = data.get('quantum_mode', False)
        
        game_obj = get_object_or_404(Game, id=game_id)
        
        # Handle quantum mode toggle
        if from_square is None and to_square is None:
            game_obj.quantum_mode = quantum_mode
            game_obj.save()
            return JsonResponse({'success': True, 'quantum_mode': game_obj.quantum_mode, 'message': 'Quantum mode updated'})
        
        from_sq = chess.parse_square(from_square) if isinstance(from_square, str) else from_square
        to_sq = chess.parse_square(to_square) if isinstance(to_square, str) else to_square
        
        board = chess.Board(fen=game_obj.fen_position)
        move = chess.Move(from_sq, to_sq)
        if promotion:
            move.promotion = chess.Piece.from_symbol(promotion).piece_type
        
        if move not in board.legal_moves:
            return JsonResponse({'success': False, 'error': 'Illegal move', 'debug': {'fen': board.fen(), 'turn': 'white' if board.turn == chess.WHITE else 'black', 'requested_move': f"{from_square}->{to_square}"}}, status=400)

        quantum_pieces_data = game_obj.quantum_pieces if game_obj.quantum_pieces else []
        from_square_name = chess.square_name(from_sq)
        to_square_name = chess.square_name(to_sq)
        
        piece = board.piece_at(from_sq)
        moved_piece_symbol = piece.symbol() if piece else None

        # Check if capturing a quantum piece (defender)
        captured_quantum_index = None
        for i, qp in enumerate(quantum_pieces_data):
            for state_id, state_data in qp.get('qnum', {}).items():
                if state_data[0] == to_square_name:
                    captured_quantum_index = i
                    break
            if captured_quantum_index is not None:
                break
        
        # Check if moving piece is quantum (attacker)
        moving_quantum_index = None
        moving_quantum_entangled = False
        for i, qp in enumerate(quantum_pieces_data):
            for state_id, state_data in qp.get('qnum', {}).items():
                if state_data[0] == from_square_name:
                    moving_quantum_index = i
                    moving_quantum_entangled = bool(qp.get('entangled'))
                    break
            if moving_quantum_index is not None:
                break
        
        is_capture = board.is_capture(move)
        
        # Make the move
        san = board.san(move)
        board.push(move)
        
        # ========================================================================
        # MEASUREMENT LOGIC - Per Game Rule/measuring.txt
        # ========================================================================
        
        # Special: If attacking piece is superposed, measure it FIRST
        if moving_quantum_index is not None and is_capture:
            print(f"DEBUG: Quantum piece at {from_square_name} made a capture")
            
            moving_qp_data = quantum_pieces_data[moving_quantum_index]
            temp_qp = QPiece(moving_qp_data.get('position', 'a1'), moving_qp_data.get('piece'))
            temp_qp.qnum = moving_qp_data.get('qnum', {'0': [moving_qp_data.get('position', 'a1'), 1]})
            
            # CASE C: Superposed + Entangled - measure() collapses ALL entangled pieces
            if moving_quantum_entangled:
                print(f"DEBUG: CASE C - Attacker is superposed AND entangled. Measuring entire entangled system.")
                measured_pos, prob = temp_qp.measure()
            else:
                # CASE A: Superposition only
                print(f"DEBUG: CASE A - Attacker is superposed only. Measuring attacker.")
                measured_pos, prob = temp_qp.measure()
            
            print(f"DEBUG: Attacking piece measured. Collapsed to {measured_pos}")
            
            quantum_pieces_data.pop(moving_quantum_index)
            
            # After measuring attacker, check if capture is still valid
            if measured_pos != from_square_name:
                temp_board = chess.Board(fen=game_obj.fen_position)
                measured_from_sq = chess.parse_square(measured_pos)
                attack_move = chess.Move(measured_from_sq, to_sq)
                
                if attack_move not in temp_board.legal_moves:
                    print(f"DEBUG: Capture failed - piece collapsed to {measured_pos} which cannot attack {to_square_name} - move fails")
                    return JsonResponse({'success': False, 'error': f'Capture failed - piece collapsed to {measured_pos}', 'fen': game_obj.fen_position})
        
        # If defending piece is superposed, measure it
        if captured_quantum_index is not None:
            print(f"DEBUG: Measuring captured (defending) piece")
            
            captured_qp_data = quantum_pieces_data[captured_quantum_index]
            captured_piece_type = captured_qp_data.get('piece')
            
            temp_qp = QPiece(captured_qp_data.get('position', 'a1'), captured_piece_type)
            temp_qp.qnum = captured_qp_data.get('qnum', {'0': [captured_qp_data.get('position', 'a1'), 1]})
            
            # Check if defending piece is also entangled
            if captured_qp_data.get('entangled'):
                print(f"DEBUG: CASE C - Defender is also entangled. Measuring entire entangled system.")
                measured_pos, prob = temp_qp.measure()
            else:
                measured_pos, prob = temp_qp.measure()
            
            print(f"DEBUG: Defending piece measured. Collapsed to {measured_pos}")
            
            quantum_pieces_data.pop(captured_quantum_index)
            
            if measured_pos == to_square_name:
                # Successful capture
                if captured_piece_type:
                    board.set_piece_at(to_sq, chess.Piece.from_symbol(captured_piece_type))
                if moved_piece_symbol:
                    board.set_piece_at(to_sq, chess.Piece.from_symbol(moved_piece_symbol))
                print(f"DEBUG: Capture succeeded - defender was at {to_square_name}")
            else:
                # Capture failed - defender was at different position
                if moved_piece_symbol:
                    board.set_piece_at(to_sq, chess.Piece.from_symbol(moved_piece_symbol))
                if captured_piece_type and measured_pos:
                    measured_sq = chess.parse_square(measured_pos)
                    board.set_piece_at(measured_sq, chess.Piece.from_symbol(captured_piece_type))
                print(f"DEBUG: Capture failed! Defender was at {measured_pos}, not {to_square_name}")
        
        # Update game status
        game_obj.status = update_game_status(board, game_obj.quantum_pieces)
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
        
        return JsonResponse({'success': True, 'fen': board.fen(), 'san': san, 'turn': 'white' if board.turn == chess.WHITE else 'black'})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def update_game_status(board, quantum_pieces):
    """Update game status considering quantum rules for king in superposition"""
    turn_color = board.turn
    
    king_square = None
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece and piece.piece_type == chess.KING and piece.color == turn_color:
            king_square = sq
            break
    
    if not king_square:
        return 'active'
    
    king_positions = [chess.square_name(king_square)]
    
    if quantum_pieces:
        for qp in quantum_pieces:
            piece_symbol = qp.get('piece', '')
            if 'K' in piece_symbol:
                for state_id, state_data in qp.get('qnum', {}).items():
                    if state_data[0]:
                        king_positions.append(state_data[0])
    
    in_check = False
    for pos in king_positions:
        sq = chess.parse_square(pos)
        if board.is_attacked_by(not turn_color, sq):
            in_check = True
            break
    
    if not in_check:
        return 'active'
    
    can_escape = False
    for pos in king_positions:
        temp_board = chess.Board(fen=board.fen())
        temp_board.turn = turn_color
        
        for move in temp_board.legal_moves:
            test_board = chess.Board(fen=temp_board.fen())
            test_board.push(move)
            new_king_sq = move.to_square
            
            if not test_board.is_attacked_by(not turn_color, new_king_sq):
                can_escape = True
                break
        
        if can_escape:
            break
    
    return 'checkmate' if not can_escape else 'active'


@csrf_exempt
@require_http_methods(["POST"])
def quantum_split(request):
    """API endpoint to perform a quantum split move"""
    try:
        data = json.loads(request.body)
        game_id = data.get('game_id')
        from_square = data.get('from_square')
        to_square1 = data.get('to_square1')
        to_square2 = data.get('to_square2')
        
        game_obj = get_object_or_404(Game, id=game_id)
        
        from_sq = chess.parse_square(from_square) if isinstance(from_square, str) else from_square
        to_sq1 = chess.parse_square(to_square1) if isinstance(to_square1, str) else to_square1
        to_sq2 = chess.parse_square(to_square2) if isinstance(to_square2, str) else to_square2
        
        quantum_pieces_data = game_obj.quantum_pieces if game_obj.quantum_pieces else []
        
        quantum_game = QuantumGame()
        quantum_game.quantum_mode = True
        
        for qp_data in quantum_pieces_data:
            qp = QPiece(qp_data.get('position', 'a1'), qp_data.get('piece'))
            qp.qnum = qp_data.get('qnum', {'0': [qp_data.get('position', 'a1'), 1]})
            quantum_game.quantum_pieces.append(qp)
        
        from_square_name = chess.square_name(from_sq)
        board = chess.Board(fen=game_obj.fen_position)
        piece = board.piece_at(from_sq)
        
        if not piece:
            return JsonResponse({'success': False, 'error': 'No piece at the source square'}, status=400)
        
        temp_board = chess.Board(fen=game_obj.fen_position)
        legal_moves = [move for move in temp_board.legal_moves if move.from_square == from_sq]
        legal_targets = {move.to_square for move in legal_moves}
        
        if to_sq1 not in legal_targets or to_sq2 not in legal_targets:
            return JsonResponse({'success': False, 'error': f'Illegal split: target squares are not valid moves'}, status=400)
        
        if board.piece_at(to_sq1) or board.piece_at(to_sq2):
            return JsonResponse({'success': False, 'error': 'Illegal split: target squares must be empty'}, status=400)
        
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
        
        quantum_pieces_data = []
        for qp in quantum_game.quantum_pieces:
            quantum_pieces_data.append({'piece': str(qp.piece), 'qnum': qp.qnum, 'entangled': [[str(e[0].piece) if e[0] else None, e[1], e[2]] for e in qp.ent]})
        
        game_obj.quantum_pieces = quantum_pieces_data
        game_obj.quantum_mode = True
        
        board.remove_piece_at(from_sq)
        board.set_piece_at(to_sq1, piece)
        board.set_piece_at(to_sq2, piece)
        board.turn = not board.turn
        game_obj.fen_position = board.fen()
        game_obj.current_turn = not game_obj.current_turn
        game_obj.status = update_game_status(board, quantum_pieces_data)
        game_obj.save()

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
        
        return JsonResponse({'success': True, 'message': 'Quantum split performed', 'from_square': from_square, 'to_square1': to_square1, 'to_square2': to_square2, 'fen': game_obj.fen_position, 'quantum_pieces': quantum_pieces_data, 'turn': 'white' if game_obj.current_turn else 'black'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def toggle_quantum_mode(request):
    try:
        data = json.loads(request.body)
        game_id = data.get('game_id')
        quantum_mode = data.get('quantum_mode', False)
        
        game_obj = get_object_or_404(Game, id=game_id)
        game_obj.quantum_mode = quantum_mode
        game_obj.save()
        
        return JsonResponse({'success': True, 'quantum_mode': game_obj.quantum_mode, 'message': 'Quantum mode ' + ('enabled' if quantum_mode else 'disabled')})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def quantum_entangle(request):
    """API endpoint to perform a quantum entanglement - CASE B"""
    try:
        data = json.loads(request.body)
        game_id = data.get('game_id')
        from_square = data.get('from_square')
        to_square = data.get('to_square')
        through_square = data.get('through_square')
        
        game_obj = get_object_or_404(Game, id=game_id)
        
        quantum_pieces_data = game_obj.quantum_pieces if game_obj.quantum_pieces else []
        quantum_game = QuantumGame()
        quantum_game.quantum_mode = True
        
        for qp_data in quantum_pieces_data:
            qp = QPiece(qp_data.get('position', 'a1'), qp_data.get('piece'))
            qp.qnum = qp_data.get('qnum', {'0': [qp_data.get('position', 'a1'), 1]})
            quantum_game.quantum_pieces.append(qp)
        
        from_sq = chess.parse_square(from_square) if isinstance(from_square, str) else from_square
        to_sq = chess.parse_square(to_square) if isinstance(to_square, str) else to_square
        through_sq = chess.parse_square(through_square) if isinstance(through_square, str) else through_square
        
        from_square_name = chess.square_name(from_sq)
        to_square_name = chess.square_name(to_sq)
        through_square_name = chess.square_name(through_sq)
        
        board = chess.Board(fen=game_obj.fen_position)
        moving_piece = board.piece_at(from_sq)
        
        if not moving_piece:
            return JsonResponse({'success': False, 'error': 'No piece at the source square'}, status=400)
        
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
        
        if blocking_quantum:
            moving_quantum = None
            for qp in quantum_game.quantum_pieces:
                for state_id, state_data in qp.qnum.items():
                    if state_data[0] == from_square_name:
                        moving_quantum = qp
                        break
                if moving_quantum:
                    break
            
            if moving_quantum:
                moving_quantum.entangle_oneblock('0', to_square_name, blocking_quantum, blocking_state)
            else:
                moving_quantum = quantum_game.add_quantum_piece(from_square_name, moving_piece.symbol())
                moving_quantum.entangle_oneblock('0', to_square_name, blocking_quantum, blocking_state)
        
        quantum_pieces_data = []
        for qp in quantum_game.quantum_pieces:
            quantum_pieces_data.append({'piece': str(qp.piece), 'qnum': qp.qnum, 'entangled': [[str(e[0].piece) if e[0] else None, e[1], e[2]] for e in qp.ent]})
        
        game_obj.quantum_pieces = quantum_pieces_data
        game_obj.save()
        
        return JsonResponse({'success': True, 'message': 'Quantum entanglement performed', 'quantum_pieces': quantum_pieces_data})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def measure_piece(request):
    """API endpoint to measure a quantum piece - handles CASE A/B/C"""
    try:
        data = json.loads(request.body)
        game_id = data.get('game_id')
        square = data.get('square')
        
        game_obj = get_object_or_404(Game, id=game_id)
        
        quantum_pieces_data = game_obj.quantum_pieces if game_obj.quantum_pieces else []
        quantum_game = QuantumGame()
        quantum_game.quantum_mode = True
        
        for qp_data in quantum_pieces_data:
            qp = QPiece(qp_data.get('position', 'a1'), qp_data.get('piece'))
            qp.qnum = qp_data.get('qnum', {'0': [qp_data.get('position', 'a1'), 1]})
            quantum_game.quantum_pieces.append(qp)
        
        result = quantum_game.measure_piece(square)
        
        if result:
            final_pos, prob = result
            
            board = chess.Board(fen=game_obj.fen_position)
            
            measured_piece = None
            for qp in quantum_game.quantum_pieces:
                for state_id, state_data in qp.qnum.items():
                    if state_data[0] == square:
                        measured_piece = qp.piece
                        break
                if measured_piece:
                    break
            
            if measured_piece:
                new_quantum_pieces = []
                for qp in quantum_game.quantum_pieces:
                    is_measured = False
                    for state_id, state_data in qp.qnum.items():
                        if state_data[0] == square:
                            is_measured = True
                            break
                    
                    if not is_measured:
                        new_quantum_pieces.append({'piece': str(qp.piece), 'qnum': qp.qnum, 'entangled': [[str(e[0].piece) if e[0] else None, e[1], e[2]] for e in qp.ent]})
                
                game_obj.quantum_pieces = new_quantum_pieces
            
            game_obj.fen_position = board.fen()
            game_obj.save()
            
            return JsonResponse({'success': True, 'message': f'Piece at {square} measured and collapsed to {final_pos}', 'final_position': final_pos, 'probability': prob, 'fen': game_obj.fen_position, 'quantum_pieces': game_obj.quantum_pieces})
        
        return JsonResponse({'success': False, 'error': f'No quantum piece found at {square}'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def get_game_state(request, game_id):
    game_obj = get_object_or_404(Game, id=game_id)
    
    moves = Move.objects.filter(game=game_obj).order_by('move_number', 'is_white_move')
    move_list = []
    for m in moves:
        move_list.append({'number': m.move_number, 'is_white': m.is_white_move, 'san': m.san, 'type': m.move_type})
    
    return JsonResponse({'game_id': game_obj.id, 'fen': game_obj.fen_position, 'turn': 'white' if game_obj.current_turn else 'black', 'quantum_mode': game_obj.quantum_mode, 'status': game_obj.status, 'moves': move_list, 'quantum_pieces': game_obj.quantum_pieces if game_obj.quantum_pieces else []})


def game_list(request):
    games = Game.objects.all()[:20]
    return render(request, 'quantum_chess/game_list.html', {'games': games})


@csrf_exempt
@require_http_methods(["POST"])
def undo_move(request):
    try:
        data = json.loads(request.body)
        game_id = data.get('game_id')
        
        game_obj = get_object_or_404(Game, id=game_id)
        
        moves = Move.objects.filter(game=game_obj).order_by('-id')
        
        if not moves.exists():
            return JsonResponse({'success': False, 'error': 'No moves to undo'}, status=400)
        
        last_move = moves.first()
        last_move.delete()
        
        if moves.count() > 0:
            previous_move = moves.order_by('-id').first()
            game_obj.fen_position = previous_move.fen_after
        else:
            game_obj.fen_position = chess.STARTING_FEN
        
        game_obj.current_turn = not game_obj.current_turn
        game_obj.status = 'active'
        game_obj.save()
        
        return JsonResponse({'success': True, 'fen': game_obj.fen_position, 'turn': 'white' if game_obj.current_turn else 'black', 'message': 'Move undone successfully'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
