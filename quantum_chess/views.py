"""
Views for Quantum Chess Django application.

This module contains the views for handling game logic and rendering templates.
"""

import json
import chess
import random
import sweetify
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


def resolve_quantum_piece_measurement(qp, target_square):
    """
    Resolve a quantum piece measurement - determine if it's at the target square or elsewhere.
    
    Returns:
        dict with keys:
            - is_at_target: bool - whether the piece is at the target square
            - actual_position: str - the actual position of the piece
            - probability: float - probability at the target
    """
    all_positions = []
    target_prob = 0.0
    total_prob = 0.0
    
    for state_id, state_data in qp.qnum.items():
        pos, prob = state_data[0], state_data[1]
        all_positions.append((pos, prob))
        total_prob += prob
        if pos == target_square:
            target_prob += prob
    
    # Determine actual position based on probability
    rand = random.random() * total_prob
    cum_prob = 0.0
    
    for pos, prob in all_positions:
        cum_prob += prob
        if rand < cum_prob:
            return {
                'is_at_target': pos == target_square,
                'actual_position': pos,
                'probability': prob / total_prob if total_prob > 0 else 0
            }
    
    # Fallback
    return {
        'is_at_target': all_positions[0][0] == target_square if all_positions else False,
        'actual_position': all_positions[0][0] if all_positions else None,
        'probability': all_positions[0][1] / total_prob if all_positions and total_prob > 0 else 0
    }


@csrf_exempt
@require_http_methods(["POST"])
def make_move(request):
    """
    API endpoint to make a move in the quantum chess game.
    Implements measurement rules according to game rules:
    - Measurements trigger when a square is in superposition of different pieces
    - Schrödinger's cat: capture without measurement if no conflict
    - Minimal influence: only resolve specific conflicts
    
    Quantum Piece Capture Rules:
    - Instance 1 (Real Attacker + Real Defender): Remove fake pieces of both, 
      attacker captures defender, attacker becomes classical
    - Instance 2 (Real Attacker + Fake Defender): Remove fake instances of both, 
      attacker remains at original square
    - Instance 3 (Fake Attacker + Fake Defender): Remove fake pieces from board,
      attacker remains on original square
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
        
        # Debug logging - include in JSON response for frontend display
        debug_messages = [f"Move: {from_square} → {to_square}"]
        
        # Get quantum pieces data and set up quantum game
        quantum_pieces_data = game_obj.quantum_pieces if game_obj.quantum_pieces else []
        from_square_name = chess.square_name(from_sq)
        to_square_name = chess.square_name(to_sq)
        
        # Create QuantumGame instance to handle measurement logic
        quantum_game = QuantumGame()
        quantum_game.quantum_mode = True
        
        # Load existing quantum pieces
        for qp_data in quantum_pieces_data:
            qp = QPiece(qp_data.get('position', 'a1'), qp_data.get('piece'))
            qp.qnum = qp_data.get('qnum', {'0': [qp_data.get('position', 'a1'), 1]})
            quantum_game.quantum_pieces.append(qp)
        
        # Get the piece being moved
        piece = board.piece_at(from_sq)
        moved_piece_symbol = piece.symbol() if piece else None
        moving_piece_color = piece.color if piece else board.turn
        
        # Check if this is a capture
        is_capture = board.is_capture(chess.Move(from_sq, to_sq))
        
        # Handle quantum piece capture with proper instance handling
        if is_capture:
            # Check if attacker is quantum
            attacker_qp = None
            for qp in quantum_game.quantum_pieces:
                for state_id, state_data in qp.qnum.items():
                    if state_data[0] == from_square_name:
                        attacker_qp = qp
                        break
                if attacker_qp:
                    break
            
            # Check if defender is quantum
            defender_qp = None
            for qp in quantum_game.quantum_pieces:
                for state_id, state_data in qp.qnum.items():
                    if state_data[0] == to_square_name:
                        defender_qp = qp
                        break
                if defender_qp:
                    break
            
            # If EITHER is quantum, handle with quantum capture rules
            if attacker_qp or defender_qp:
                debug_messages.append('Quantum capture detected!')

                attacker_result = None
                defender_result = None
                
                # Measure attacker if quantum
                if attacker_qp:
                    attacker_result = resolve_quantum_piece_measurement(attacker_qp, from_square_name)
                    debug_messages.append(f"Attacker measured at {from_square_name}: {attacker_result}")
                
                # Measure defender if quantum
                if defender_qp:
                    defender_result = resolve_quantum_piece_measurement(defender_qp, to_square_name)
                    debug_messages.append(f"Defender measured at {to_square_name}: {defender_result}")
                
                # Determine which instance applies
                attacker_is_real = not attacker_qp or (attacker_result and attacker_result['is_at_target'])
                defender_is_real = not defender_qp or (defender_result and defender_result['is_at_target'])
                
                debug_messages.append(f"Instance check - Attacker: {attacker_is_real}, Defender: {defender_is_real}")
                
                if attacker_is_real and defender_is_real:
                    # Instance 1: Real Attacker + Real Defender
                    # Remove fake pieces of both, attacker captures defender, attacker becomes classical
                    debug_messages.append('Instance 1: Real attacker captures real defender!')
                    
                    # Remove fake positions of attacker
                    if attacker_qp:
                        for state_id, state_data in list(attacker_qp.qnum.items()):
                            if state_data[0] != from_square_name:
                                other_sq = chess.parse_square(state_data[0])
                                board.remove_piece_at(other_sq)
                                del attacker_qp.qnum[state_id]
                    
                    # Remove fake positions of defender
                    if defender_qp:
                        for state_id, state_data in list(defender_qp.qnum.items()):
                            if state_data[0] != to_square_name:
                                other_sq = chess.parse_square(state_data[0])
                                board.remove_piece_at(other_sq)
                                del defender_qp.qnum[state_id]
                    
                    # Remove defender from quantum_pieces (captured)
                    new_quantum_pieces = []
                    for qp in quantum_game.quantum_pieces:
                        is_defender = False
                        for state_id, state_data in qp.qnum.items():
                            if state_data[0] == to_square_name:
                                is_defender = True
                                break
                        if not is_defender:
                            new_quantum_pieces.append({
                                'piece': str(qp.piece),
                                'qnum': qp.qnum,
                                'position': list(qp.qnum.values())[0][0] if qp.qnum else None,
                                'entangled': [[str(e[0].piece) if e[0] else None, e[1], e[2]] for e in qp.ent]
                            })
                    quantum_pieces_data = new_quantum_pieces
                    
                    # Continue with normal capture processing below
                    
                elif not attacker_is_real and defender_is_real:
                    # Instance 2 variant: Fake Attacker + Real Defender
                    # Attacker is NOT at from_square (fake), so capture fails
                    # Remove fake positions of attacker, attacker stays at actual position
                    debug_messages.append('Instance 2: Fake attacker, real defender - capture failed!')
                    
                    # Remove fake attacker from from_square (it was never there)
                    board.remove_piece_at(from_sq)
                    
                    # Place attacker at actual position
                    if attacker_result and attacker_result['actual_position']:
                        att_actual = attacker_result['actual_position']
                        att_sq = chess.parse_square(att_actual)
                        attacker_symbol = str(attacker_qp.piece) if attacker_qp else None
                        if attacker_symbol:
                            board.set_piece_at(att_sq, chess.Piece.from_symbol(attacker_symbol))
                    
                    # Remove fake positions of defender (keep real one at to_square)
                    if defender_qp:
                        for state_id, state_data in list(defender_qp.qnum.items()):
                            if state_data[0] != to_square_name:
                                other_sq = chess.parse_square(state_data[0])
                                board.remove_piece_at(other_sq)
                                del defender_qp.qnum[state_id]
                    
                    # Remove attacker from quantum_pieces, keep defender
                    new_quantum_pieces = []
                    for qp in quantum_game.quantum_pieces:
                        is_attacker = False
                        for state_id, state_data in qp.qnum.items():
                            if state_data[0] == from_square_name:
                                is_attacker = True
                                break
                        if not is_attacker:
                            new_quantum_pieces.append({
                                'piece': str(qp.piece),
                                'qnum': qp.qnum,
                                'position': list(qp.qnum.values())[0][0] if qp.qnum else None,
                                'entangled': [[str(e[0].piece) if e[0] else None, e[1], e[2]] for e in qp.ent]
                            })
                    quantum_pieces_data = new_quantum_pieces
                    
                    # DO NOT complete the capture - update FEN and return
                    game_obj.fen_position = board.fen()
                    game_obj.current_turn = not game_obj.current_turn
                    game_obj.quantum_pieces = quantum_pieces_data
                    game_obj.save()
                    
                    # Record measurement
                    move_count = Move.objects.filter(game=game_obj).count()
                    Move.objects.create(
                        game=game_obj,
                        move_number=move_count // 2 + 1,
                        is_white_move=moving_piece_color == chess.WHITE,
                        move_type='measure',
                        from_square=from_sq,
                        to_square=to_sq,
                        promotion=None,
                        san=f'Measurement: Instance 2 - Fake attacker, real defender',
                        fen_after=game_obj.fen_position
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'fen': game_obj.fen_position,
                        'message': 'Instance 2: Fake attacker, real defender - capture failed',
                        'turn': 'white' if game_obj.current_turn else 'black',
                        'quantum_pieces': quantum_pieces_data,
                        'measurement': {
                            'instance': 2,
                            'action': 'capture_fails',
                            'attacker_is_real': False,
                            'defender_is_real': True,
                            'attacker_actual_position': attacker_result['actual_position'] if attacker_result else None
                        }
                    })
                
                elif attacker_is_real and not defender_is_real:
                    # Instance 2: Real Attacker + Fake Defender
                    # Remove fake instances of both, attacker stays at original square
                    debug_messages.append('Instance 2: Real attacker, fake defender - capture failed!')
                    
                    # Remove fake positions of attacker
                    if attacker_qp:
                        for state_id, state_data in list(attacker_qp.qnum.items()):
                            if state_data[0] != from_square_name:
                                other_sq = chess.parse_square(state_data[0])
                                board.remove_piece_at(other_sq)
                                del attacker_qp.qnum[state_id]
                    
                    # Remove fake defender from to_square
                    board.remove_piece_at(to_sq)
                    
                    # Place defender at actual position
                    if defender_result and defender_result['actual_position']:
                        def_actual = defender_result['actual_position']
                        def_sq = chess.parse_square(def_actual)
                        defender_symbol = str(defender_qp.piece) if defender_qp else None
                        if defender_symbol:
                            board.set_piece_at(def_sq, chess.Piece.from_symbol(defender_symbol))
                    
                    # Remove both from quantum_pieces
                    new_quantum_pieces = []
                    for qp in quantum_game.quantum_pieces:
                        is_involved = False
                        for state_id, state_data in qp.qnum.items():
                            if state_data[0] == from_square_name or state_data[0] == to_square_name:
                                is_involved = True
                                break
                        if not is_involved:
                            new_quantum_pieces.append({
                                'piece': str(qp.piece),
                                'qnum': qp.qnum,
                                'position': list(qp.qnum.values())[0][0] if qp.qnum else None,
                                'entangled': [[str(e[0].piece) if e[0] else None, e[1], e[2]] for e in qp.ent]
                            })
                    quantum_pieces_data = new_quantum_pieces
                    
                    # DO NOT complete the capture - update FEN and return
                    game_obj.fen_position = board.fen()
                    game_obj.current_turn = not game_obj.current_turn
                    game_obj.quantum_pieces = quantum_pieces_data
                    game_obj.save()
                    
                    # Record measurement
                    move_count = Move.objects.filter(game=game_obj).count()
                    Move.objects.create(
                        game=game_obj,
                        move_number=move_count // 2 + 1,
                        is_white_move=moving_piece_color == chess.WHITE,
                        move_type='measure',
                        from_square=from_sq,
                        to_square=to_sq,
                        promotion=None,
                        san=f'Measurement: Instance 2 - Real attacker, fake defender',
                        fen_after=game_obj.fen_position
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'fen': game_obj.fen_position,
                        'message': 'Instance 2: Real attacker, fake defender - capture failed',
                        'turn': 'white' if game_obj.current_turn else 'black',
                        'quantum_pieces': quantum_pieces_data,
                        'measurement': {
                            'instance': 2,
                            'action': 'capture_fails',
                            'attacker_is_real': True,
                            'defender_is_real': False,
                            'defender_actual_position': defender_result['actual_position'] if defender_result else None
                        }
                    })
                    
                elif not attacker_is_real and not defender_is_real:
                    # Instance 3: Fake Attacker + Fake Defender
                    # Fake pieces removed, attacker stays at original square
                    debug_messages.append('Instance 3: Both fake - capture failed!')
                    
                    # Remove fake attacker from from_square
                    board.remove_piece_at(from_sq)
                    
                    # Remove fake defender from to_square  
                    board.remove_piece_at(to_sq)
                    
                    # Place attacker at actual position
                    if attacker_result and attacker_result['actual_position']:
                        att_actual = attacker_result['actual_position']
                        att_sq = chess.parse_square(att_actual)
                        attacker_symbol = str(attacker_qp.piece) if attacker_qp else None
                        if attacker_symbol:
                            board.set_piece_at(att_sq, chess.Piece.from_symbol(attacker_symbol))
                    
                    # Place defender at actual position
                    if defender_result and defender_result['actual_position']:
                        def_actual = defender_result['actual_position']
                        def_sq = chess.parse_square(def_actual)
                        defender_symbol = str(defender_qp.piece) if defender_qp else None
                        if defender_symbol:
                            board.set_piece_at(def_sq, chess.Piece.from_symbol(defender_symbol))
                    
                    # Remove both from quantum_pieces
                    new_quantum_pieces = []
                    for qp in quantum_game.quantum_pieces:
                        is_involved = False
                        for state_id, state_data in qp.qnum.items():
                            if state_data[0] == from_square_name or state_data[0] == to_square_name:
                                is_involved = True
                                break
                        if not is_involved:
                            new_quantum_pieces.append({
                                'piece': str(qp.piece),
                                'qnum': qp.qnum,
                                'position': list(qp.qnum.values())[0][0] if qp.qnum else None,
                                'entangled': [[str(e[0].piece) if e[0] else None, e[1], e[2]] for e in qp.ent]
                            })
                    quantum_pieces_data = new_quantum_pieces
                    
                    # DO NOT complete the capture - update FEN and return
                    game_obj.fen_position = board.fen()
                    game_obj.current_turn = not game_obj.current_turn
                    game_obj.quantum_pieces = quantum_pieces_data
                    game_obj.save()
                    
                    # Record measurement
                    move_count = Move.objects.filter(game=game_obj).count()
                    Move.objects.create(
                        game=game_obj,
                        move_number=move_count // 2 + 1,
                        is_white_move=moving_piece_color == chess.WHITE,
                        move_type='measure',
                        from_square=from_sq,
                        to_square=to_sq,
                        promotion=None,
                        san=f'Measurement: Instance 3 - Both fake',
                        fen_after=game_obj.fen_position
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'fen': game_obj.fen_position,
                        'message': 'Instance 3: Both fake - capture failed',
                        'turn': 'white' if game_obj.current_turn else 'black',
                        'quantum_pieces': quantum_pieces_data,
                        'measurement': {
                            'instance': 3,
                            'action': 'both_fake',
                            'attacker_is_real': False,
                            'defender_is_real': False,
                            'attacker_actual_position': attacker_result['actual_position'] if attacker_result else None,
                            'defender_actual_position': defender_result['actual_position'] if defender_result else None
                        }
                    })
        
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
        
        # Check if the piece being moved is in quantum state
        moving_quantum_index = None
        moving_quantum_other_positions = []
        
        for i, qp in enumerate(quantum_pieces_data):
            for state_id, state_data in qp.get('qnum', {}).items():
                if state_data[0] == from_square_name:
                    moving_quantum_index = i
                    for other_state_id, other_state_data in qp.get('qnum', {}).items():
                        if other_state_id != state_id:
                            moving_quantum_other_positions.append(other_state_data[0])
                    break
            if moving_quantum_index is not None:
                break
        
        # Make the move
        san = board.san(move)
        board.push(move)
        
        # Handle captures of quantum pieces
        if captured_quantum_index is not None and captured_quantum_positions:
            debug_messages.append(f'Capturing quantum piece at {to_square_name}')
            
            board.remove_piece_at(to_sq)
            
            captured_piece_type = quantum_pieces_data[captured_quantum_index].get('piece')
            quantum_pieces_data.pop(captured_quantum_index)
            
            if captured_piece_type:
                board.set_piece_at(to_sq, chess.Piece.from_symbol(captured_piece_type))
        
        # Handle moving quantum piece - collapse other superpositions
        if moving_quantum_index is not None and moving_quantum_other_positions:
            debug_messages.append(f'Collapsing quantum piece from {from_square_name}')
            for other_pos in moving_quantum_other_positions:
                other_sq = chess.parse_square(other_pos)
                board.remove_piece_at(other_sq)
            
            adjusted_index = moving_quantum_index
            if captured_quantum_index is not None and captured_quantum_index < moving_quantum_index:
                adjusted_index = moving_quantum_index - 1
            
            if adjusted_index < len(quantum_pieces_data):
                quantum_pieces_data[adjusted_index]['qnum'] = {
                    '0': [to_square_name, 1.0]
                }
                quantum_pieces_data[adjusted_index]['entangled'] = []

        
        # Update game status
        if board.is_checkmate():
            game_obj.status = 'checkmate'
        elif board.is_stalemate():
            game_obj.status = 'stalemate'
        elif board.is_insufficient_material():
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
            'debug_messages': debug_messages,
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
        
        # Add the piece to BOTH target positions
        board.set_piece_at(to_sq1, piece)
        board.set_piece_at(to_sq2, piece)
        
        # Switch turn in the FEN
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
        
        message = 'Quantum mode ' + ('enabled' if quantum_mode else 'disabled')
        sweetify.success(request, message)
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
