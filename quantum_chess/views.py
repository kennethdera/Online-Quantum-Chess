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
    Implements measurement rules according to game rules:
    - Measurements trigger when a square is in superposition of different pieces
    - Schrödinger's cat: capture without measurement if no conflict
    - Minimal influence: only resolve specific conflicts
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
        
        # === MEASUREMENT DETECTION (Game Rules) ===
        # Check if this move should trigger a measurement
        # Measurement ONLY happens during captures
        is_capture = board.is_capture(chess.Move(from_sq, to_sq))
        
        # Check if the SOURCE piece (the one attempting to capture) is a quantum piece
        # This is a new rule: when a quantum piece attempts to capture, resolve which position is original first
        quantum_capturer_result = None
        if is_capture:
            # Check if the moving piece is a quantum piece at from_square
            quantum_capturer_result = quantum_game.is_quantum_capturer(from_square_name)
            if quantum_capturer_result:
                print(f"DEBUG: Quantum piece at {from_square_name} is attempting to capture - resolving measurement first")
                # Resolve the quantum capturer measurement before proceeding
                quantum_capturer_measurement = quantum_game.resolve_quantum_capturer_measurement(
                    from_square_name, to_square_name, moving_piece_color
                )
                
                if quantum_capturer_measurement.get('success'):
                    action = quantum_capturer_measurement.get('action')
                    selected_piece = quantum_capturer_measurement.get('selected_piece')
                    print(f"DEBUG: Quantum capturer measurement resolved - {quantum_capturer_measurement}")
                    
                    if action == 'capture_succeeds':
                        # The RIGHT piece is capturing - it's actually at from_square
                        # 1. Remove other instances from board (FEN)
                        # 2. Execute the capture
                        # 3. Change capturing piece to classical piece
                        
                        other_positions_removed = quantum_capturer_measurement.get('other_positions_removed', [])
                        
                        # Remove other quantum positions from the board
                        for pos, prob in other_positions_removed:
                            other_sq = chess.parse_square(pos)
                            board.remove_piece_at(other_sq)
                            print(f"DEBUG: Removed {selected_piece} from {pos} (other quantum position)")
                        
                        # The capture will be processed normally below
                        # The piece will become classical after the capture
                        quantum_capturer_result = quantum_capturer_measurement
                        
                    elif action == 'capture_fails_make_classical':
                        # The WRONG piece is attempting to capture - piece is actually at another position
                        # Capture fails, piece becomes classical at actual position
                        
                        actual_position = quantum_capturer_measurement.get('actual_position')
                        
                        print(f"DEBUG: Capture fails - {selected_piece} is NOT at {from_square_name}")
                        print(f"DEBUG: Actual position is at {actual_position} - converting to classical")
                        
                        # Remove the piece from from_square (it was never there)
                        board.remove_piece_at(from_sq)
                        print(f"DEBUG: Removed fake piece from {from_square_name}")
                        
                        # Place the piece as classical at the actual position on the board
                        if actual_position:
                            actual_sq = chess.parse_square(actual_position)
                            board.set_piece_at(actual_sq, chess.Piece.from_symbol(selected_piece))
                            print(f"DEBUG: Placed classical piece {selected_piece} at {actual_position}")
                        
                        # ALSO measure any quantum piece at the destination square (to_square)
                        # This is important - the defender also needs to be resolved!
                        import random as random_module
                        defender_measured = False
                        defender_actual_pos = None
                        defender_piece_symbol = None
                        
                        for i, qp in enumerate(quantum_game.quantum_pieces):
                            for state_id, state_data in qp.qnum.items():
                                if state_data[0] == to_square_name:
                                    # There's a quantum piece at the destination - measure it!
                                    defender_piece_symbol = str(qp.piece)
                                    print(f"DEBUG: Found quantum defender {defender_piece_symbol} at {to_square_name} - measuring it")
                                    
                                    # Get all positions for this piece
                                    all_positions = [(sid, sd[0], sd[1]) for sid, sd in qp.qnum.items()]
                                    
                                    # Randomly determine actual position
                                    total_prob = sum(p for _, _, p in all_positions)
                                    rand = random_module.random()
                                    cum_prob = 0
                                    
                                    for sid, pos, prob in all_positions:
                                        cum_prob += prob / total_prob
                                        if rand < cum_prob:
                                            defender_actual_pos = pos
                                            break
                                    
                                    if defender_actual_pos is None:
                                        defender_actual_pos = all_positions[0][1]
                                    
                                    print(f"DEBUG: Defender {defender_piece_symbol} measured - actual position: {defender_actual_pos}")
                                    
                                    # Remove from destination (fake position)
                                    board.remove_piece_at(to_sq)
                                    
                                    # Place at actual position as classical
                                    if defender_actual_pos:
                                        def_actual_sq = chess.parse_square(defender_actual_pos)
                                        board.set_piece_at(def_actual_sq, chess.Piece.from_symbol(defender_piece_symbol))
                                        print(f"DEBUG: Placed defender {defender_piece_symbol} at actual position {defender_actual_pos}")
                                    
                                    # Don't add to quantum_pieces - it's now classical
                                    defender_measured = True
                                    break
                            
                            if defender_measured:
                                break
                        
                        # Remove the quantum pieces from quantum_pieces_data (they become classical)
                        quantum_pieces_data = []
                        for qp in quantum_game.quantum_pieces:
                            piece_str = str(qp.piece)
                            
                            # Skip the attacker piece (became classical)
                            if piece_str == selected_piece:
                                print(f"DEBUG: Removing quantum piece {selected_piece} from quantum_pieces (became classical)")
                                continue
                            
                            # Skip the defender piece if it was measured
                            if defender_measured and piece_str == defender_piece_symbol:
                                print(f"DEBUG: Removing quantum piece {defender_piece_symbol} from quantum_pieces (became classical)")
                                continue
                            
                            quantum_pieces_data.append({
                                'piece': piece_str,
                                'qnum': qp.qnum,
                                'entangled': [[str(e[0].piece) if e[0] else None, e[1], e[2]] for e in qp.ent]
                            })
                        
                        # IMPORTANT: DO NOT complete the capture - the piece was never at from_square
                        # Update game state without making the capture move
                        game_obj.quantum_pieces = quantum_pieces_data
                        game_obj.fen_position = board.fen()
                        game_obj.current_turn = not game_obj.current_turn
                        game_obj.save()
                        
                        # Record measurement in move history
                        move_count = Move.objects.filter(game=game_obj).count()
                        measurement_note = f'Measurement: {selected_piece} not at {from_square_name}, at {actual_position}'
                        if defender_measured:
                            measurement_note += f'; {defender_piece_symbol} at {to_square_name} measured to {defender_actual_pos}'
                        
                        Move.objects.create(
                            game=game_obj,
                            move_number=move_count // 2 + 1,
                            is_white_move=moving_piece_color == chess.WHITE,
                            move_type='measure',
                            from_square=from_sq,
                            to_square=to_sq,
                            promotion=None,
                            san=measurement_note,
                            fen_after=game_obj.fen_position
                        )
                        
                        return JsonResponse({
                            'success': True,
                            'fen': game_obj.fen_position,
                            'message': f'Capture failed! {selected_piece} was not at {from_square_name}. Found at {actual_position}. Defender {defender_piece_symbol} at {to_square_name} measured to {defender_actual_pos}.' if defender_measured else f'Capture failed! {selected_piece} was not at {from_square_name}. Found at {actual_position}.',
                            'turn': 'white' if game_obj.current_turn else 'black',
                            'quantum_pieces': quantum_pieces_data,
                            'measurement': {
                                'action': 'capture_fails_make_classical',
                                'selected_piece': selected_piece,
                                'attempted_from': from_square_name,
                                'actual_position': actual_position,
                                'defender_measured': defender_measured,
                                'defender_piece': defender_piece_symbol,
                                'defender_actual_position': defender_actual_pos
                            } if defender_measured else {
                                'action': 'capture_fails_make_classical',
                                'selected_piece': selected_piece,
                                'attempted_from': from_square_name,
                                'actual_position': actual_position
                            }
                        })
                    
                    elif action == 'capture_fails_no_position':
                        # The piece doesn't exist at all
                        print(f"DEBUG: Capture fails - {selected_piece} does NOT exist at {from_square_name}")
                        
                        # Remove from board
                        board.remove_piece_at(from_sq)
                        
                        # Remove from quantum pieces
                        quantum_pieces_data = []
                        for qp in quantum_game.quantum_pieces:
                            if str(qp.piece) != selected_piece:
                                quantum_pieces_data.append({
                                    'piece': str(qp.piece),
                                    'qnum': qp.qnum,
                                    'entangled': [[str(e[0].piece) if e[0] else None, e[1], e[2]] for e in qp.ent]
                                })
                        
                        # Update game state without making the capture move
                        game_obj.quantum_pieces = quantum_pieces_data
                        game_obj.fen_position = board.fen()
                        game_obj.current_turn = not game_obj.current_turn
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
                            san=f'Measurement: {selected_piece} does not exist at {from_square_name}',
                            fen_after=game_obj.fen_position
                        )
                        
                        return JsonResponse({
                            'success': True,
                            'fen': game_obj.fen_position,
                            'message': f'Capture failed! {selected_piece} does not exist at {from_square_name}.',
                            'turn': 'white' if game_obj.current_turn else 'black',
                            'quantum_pieces': quantum_pieces_data,
                            'measurement': {
                                'action': 'capture_fails_no_position',
                                'selected_piece': selected_piece,
                                'attempted_from': from_square_name
                            }
                        })
        
        should_measure, conflict_square, other_square = quantum_game.should_trigger_measurement(
            from_square_name, to_square_name, moving_piece_color, is_capture
        )
        
        measurement_result = None
        
        # BUG FIX: When BOTH source and destination have quantum pieces, measure BOTH!
        # other_square contains the other square that needs measurement
        if should_measure and conflict_square:
            
            # Check if defender at destination is also a quantum piece - this is the key case!
            defender_is_quantum = quantum_game.find_quantum_piece_at(to_square_name)
            
            # Only use quantum vs quantum method when BOTH attacker and defender are quantum
            if other_square and other_square != conflict_square and defender_is_quantum:
                print(f"DEBUG: Quantum vs Quantum capture detected!")
                
                # Use the new unified method that handles all three instances
                quantum_vs_quantum_result = quantum_game.resolve_quantum_vs_quantum_capture(
                    from_square_name, to_square_name, moving_piece_color
                )
                
                if quantum_vs_quantum_result.get('success'):
                    instance = quantum_vs_quantum_result.get('instance')
                    action = quantum_vs_quantum_result.get('action')
                    attacker_piece = quantum_vs_quantum_result.get('attacker_piece')
                    defender_piece = quantum_vs_quantum_result.get('defender_piece')
                    
                    print(f"DEBUG: Quantum vs Quantum capture - Instance {instance}: {action}")
                    print(f"DEBUG: {quantum_vs_quantum_result.get('message')}")
                    
                    # Handle each instance
                    if instance == 1:
                        # Instance 1: Real Attacker + Real Defender - Capture succeeds
                        # Remove fake pieces of both from the board
                        attacker_other = quantum_vs_quantum_result.get('attacker_other_positions', [])
                        defender_other = quantum_vs_quantum_result.get('defender_other_positions', [])
                        
                        for pos, prob in attacker_other:
                            other_sq = chess.parse_square(pos)
                            board.remove_piece_at(other_sq)
                            print(f"DEBUG: Removed attacker fake piece from {pos}")
                        
                        for pos, prob in defender_other:
                            other_sq = chess.parse_square(pos)
                            board.remove_piece_at(other_sq)
                            print(f"DEBUG: Removed defender fake piece from {pos}")
                        
                        # Remove both pieces from quantum_pieces (they become classical)
                        quantum_pieces_data = []
                        
                    elif instance == 2:
                        # Instance 2: Real Attacker + Fake Defender - Capture fails
                        attacker_other = quantum_vs_quantum_result.get('attacker_other_positions', [])
                        defender_actual = quantum_vs_quantum_result.get('defender_actual_position')
                        
                        # Remove attacker's other positions from board
                        for pos, prob in attacker_other:
                            other_sq = chess.parse_square(pos)
                            board.remove_piece_at(other_sq)
                        
                        # Remove fake defender from to_square
                        board.remove_piece_at(to_sq)
                        
                        # Place defender at actual position as classical
                        if defender_actual:
                            def_sq = chess.parse_square(defender_actual)
                            board.set_piece_at(def_sq, chess.Piece.from_symbol(defender_piece))
                        
                        # Update FEN and return without completing capture
                        game_obj.fen_position = board.fen()
                        game_obj.current_turn = not game_obj.current_turn
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
                            'message': f'Instance 2: Real attacker {attacker_piece} at {from_square_name}, fake defender {defender_piece} at {to_square_name} (actual: {defender_actual})',
                            'turn': 'white' if game_obj.current_turn else 'black',
                            'quantum_pieces': [],
                            'measurement': {
                                'instance': 2,
                                'action': 'capture_fails',
                                'attacker_piece': attacker_piece,
                                'defender_piece': defender_piece,
                                'defender_actual_position': defender_actual
                            }
                        })
                    
                    elif instance == 3:
                        # Instance 3: Fake Attacker + Fake Defender - Both fake
                        attacker_actual = quantum_vs_quantum_result.get('attacker_actual_position')
                        defender_actual = quantum_vs_quantum_result.get('defender_actual_position')
                        
                        # Remove fake pieces from both attempted squares
                        board.remove_piece_at(from_sq)
                        board.remove_piece_at(to_sq)
                        
                        # Place pieces at their actual positions as classical
                        if attacker_actual:
                            att_sq = chess.parse_square(attacker_actual)
                            board.set_piece_at(att_sq, chess.Piece.from_symbol(attacker_piece))
                        
                        if defender_actual:
                            def_sq = chess.parse_square(defender_actual)
                            board.set_piece_at(def_sq, chess.Piece.from_symbol(defender_piece))
                        
                        # Update FEN and return without completing capture
                        game_obj.fen_position = board.fen()
                        game_obj.current_turn = not game_obj.current_turn
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
                            'message': f'Instance 3: Fake attacker {attacker_piece} at {from_square_name} (actual: {attacker_actual}), fake defender {defender_piece} at {to_square_name} (actual: {defender_actual})',
                            'turn': 'white' if game_obj.current_turn else 'black',
                            'quantum_pieces': [],
                            'measurement': {
                                'instance': 3,
                                'action': 'both_fake',
                                'attacker_piece': attacker_piece,
                                'defender_piece': defender_piece,
                                'attacker_actual_position': attacker_actual,
                                'defender_actual_position': defender_actual
                            }
                        })
                    
                    # For instance 1 (capture succeeds), continue to process the capture below
                    measurement_result = quantum_vs_quantum_result
            
            # Now measure the defender (destination square) if there's still a quantum piece there
            print(f"DEBUG: Measurement triggered at {conflict_square} (capture mode)")

            # Collect all positions of quantum pieces at the conflict square BEFORE measurement
            all_quantum_positions = {}
            for qp in quantum_game.quantum_pieces:
                piece_symbol = str(qp.piece)
                positions = []
                for state_id, state_data in qp.qnum.items():
                    if state_data[0] == conflict_square:
                        # This piece is at the conflict square
                        # Collect all its positions
                        for all_state_id, all_state_data in qp.qnum.items():
                            positions.append(all_state_data[0])
                        all_quantum_positions[piece_symbol] = positions
                        break

            # Resolve the measurement according to game rules for captures
            # This implements: if piece IS the right one -> remove other instances, let capture succeed
            # If piece is NOT the right one -> return opponent piece to original, make right position classical
            measurement_result = quantum_game.resolve_capture_measurement(
                conflict_square, moving_piece_color, is_capturing=True
            )

            if measurement_result.get('success'):
                print(f"DEBUG: Measurement resolved - {measurement_result}")

                # Handle different measurement outcomes
                action = measurement_result.get('action')

                if action == 'capture_succeeds':
                    # The piece IS at the capture square - remove other instances, let capture proceed

                    # Get the selected piece info from measurement result
                    selected_piece = measurement_result.get('selected_piece')

                    # Remove pieces from other quantum positions for the selected piece
                    if selected_piece in all_quantum_positions:
                        for pos in all_quantum_positions[selected_piece]:
                            if pos != conflict_square:
                                other_sq = chess.parse_square(pos)
                                board.remove_piece_at(other_sq)
                                print(f"DEBUG: Removed {selected_piece} from {pos} (other quantum position)")

                    # Place the piece at the capture square as classical (since it exists there)
                    conflict_sq = chess.parse_square(conflict_square)
                    board.set_piece_at(conflict_sq, chess.Piece.from_symbol(selected_piece))
                    print(f"DEBUG: Placed {selected_piece} at {conflict_square} as classical piece")

                    # Remove the measured piece from quantum_game.quantum_pieces entirely (becomes classical)
                    quantum_game.quantum_pieces = [
                        qp for qp in quantum_game.quantum_pieces
                        if str(qp.piece) != selected_piece
                    ]
                    print(f"DEBUG: Removed {selected_piece} from quantum_game.quantum_pieces (became classical)")

                    # Update quantum pieces data after measurement - this removes other instances
                    quantum_pieces_data = []
                    for qp in quantum_game.quantum_pieces:
                        quantum_pieces_data.append({
                            'piece': str(qp.piece),
                            'qnum': qp.qnum,
                            'entangled': [[str(e[0].piece) if e[0] else None, e[1], e[2]] for e in qp.ent]
                        })
                    
                    # Record measurement in move history
                    move_count = Move.objects.filter(game=game_obj).count()
                    Move.objects.create(
                        game=game_obj,
                        move_number=move_count // 2 + 1,
                        is_white_move=moving_piece_color == chess.WHITE,
                        move_type='measure',
                        from_square=from_sq,
                        to_square=to_sq,
                        promotion=None,
                        san=f'Measurement at {conflict_square}',
                        fen_after=board.fen()
                    )
                    
                    # Since measurement already handled the capture, skip the capture processing below
                    # Set these to None to prevent double-processing
                    captured_quantum_index = None
                    captured_quantum_positions = []
                    
                    # DO NOT RETURN HERE - Continue to process the capture below
                    
                elif action == 'capture_fails_make_classical':
                    # The piece is NOT at the capture square - this is the "wrong one" case
                    # According to rules: return opponent piece to original square, 
                    # remove false positions, turn right position to classical piece
                    
                    selected_piece = measurement_result.get('selected_piece')
                    new_position = measurement_result.get('new_position')
                    
                    print(f"DEBUG: Capture failed - piece {selected_piece} is NOT at {conflict_square}")
                    print(f"DEBUG: Actual position is at {new_position} - converting to classical")
                    
                    # First, remove the fake piece from the capture square on the FEN board
                    # The piece was never actually at the capture square
                    board = chess.Board(fen=game_obj.fen_position)
                    conflict_sq = chess.parse_square(conflict_square)
                    board.remove_piece_at(conflict_sq)
                    print(f"DEBUG: Removed fake piece from {conflict_square}")
                    
                    # Remove the quantum piece from quantum_pieces_data (it becomes classical)
                    quantum_pieces_data = []
                    for qp in quantum_game.quantum_pieces:
                        # Check if this quantum piece has the selected piece type
                        if str(qp.piece) == selected_piece:
                            # Check if it has other positions besides the conflict square
                            has_other_positions = False
                            for state_id, state_data in qp.qnum.items():
                                if state_data[0] != conflict_square:
                                    has_other_positions = True
                                    break
                            
                            if not has_other_positions:
                                # This is the piece to convert to classical
                                print(f"DEBUG: Removing quantum piece {selected_piece} from quantum_pieces (becomes classical)")
                                continue  # Skip adding to quantum_pieces_data - it's now classical
                        
                        quantum_pieces_data.append({
                            'piece': str(qp.piece),
                            'qnum': qp.qnum,
                            'entangled': [[str(e[0].piece) if e[0] else None, e[1], e[2]] for e in qp.ent]
                        })
                    
                    # Place the piece as classical at the new position on the board
                    # This is where the piece actually is (the non-captured position)
                    if new_position:
                        new_sq = chess.parse_square(new_position)
                        board.set_piece_at(new_sq, chess.Piece.from_symbol(selected_piece))
                        game_obj.fen_position = board.fen()
                        print(f"DEBUG: Placed classical piece {selected_piece} at {new_position}")
                    
                    # IMPORTANT: DO NOT complete the capture - return opponent piece to original square
                    # The capturing piece stays at its original position, capture fails
                    # Need to return here without executing the capture move
                    
                    # Update game state without making the capture move
                    game_obj.quantum_pieces = quantum_pieces_data
                    game_obj.current_turn = not game_obj.current_turn
                    game_obj.save()
                    
                    # Record measurement in move history
                    move_count = Move.objects.filter(game=game_obj).count()
                    Move.objects.create(
                        game=game_obj,
                        move_number=move_count // 2 + 1,
                        is_white_move=moving_piece_color == chess.WHITE,
                        move_type='measure',
                        from_square=from_sq,
                        to_square=to_sq,
                        promotion=None,
                        san=f'Measurement: {selected_piece} not at {conflict_square}, at {new_position}',
                        fen_after=game_obj.fen_position
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'fen': game_obj.fen_position,
                        'message': f'Capture failed! {selected_piece} was not at {conflict_square}. Found at {new_position}.',
                        'turn': 'white' if game_obj.current_turn else 'black',
                        'quantum_pieces': quantum_pieces_data,
                        'measurement': {
                            'action': 'capture_fails_make_classical',
                            'selected_piece': selected_piece,
                            'capture_square': conflict_square,
                            'actual_position': new_position
                        }
                    })
                elif action == 'capture_fails_no_position':
                    # The piece doesn't exist at all - just remove from quantum pieces
                    # The capture also fails (no piece to capture)
                    
                    selected_piece = measurement_result.get('selected_piece')
                    
                    print(f"DEBUG: Capture failed - {selected_piece} does NOT exist at {conflict_square}")
                    
                    # Remove all quantum pieces at this square
                    quantum_pieces_data = []
                    for qp in quantum_game.quantum_pieces:
                        # Check if this quantum piece is at the capture square
                        is_at_capture_square = False
                        for state_id, state_data in qp.qnum.items():
                            if state_data[0] == conflict_square:
                                is_at_capture_square = True
                                break
                        
                        if not is_at_capture_square:
                            # Keep this quantum piece
                            quantum_pieces_data.append({
                                'piece': str(qp.piece),
                                'qnum': qp.qnum,
                                'entangled': [[str(e[0].piece) if e[0] else None, e[1], e[2]] for e in qp.ent]
                            })
                        # Skip adding the piece at capture square - it doesn't exist
                    
                    # IMPORTANT: DO NOT complete the capture - return opponent piece to original square
                    # We need to return here without executing the capture move
                    
                    # Update game state without making the capture move
                    game_obj.quantum_pieces = quantum_pieces_data
                    game_obj.current_turn = not game_obj.current_turn
                    game_obj.save()
                    
                    # Record measurement in move history
                    move_count = Move.objects.filter(game=game_obj).count()
                    Move.objects.create(
                        game=game_obj,
                        move_number=move_count // 2 + 1,
                        is_white_move=moving_piece_color == chess.WHITE,
                        move_type='measure',
                        from_square=from_sq,
                        to_square=to_sq,
                        promotion=None,
                        san=f'Measurement: {selected_piece} does not exist at {conflict_square}',
                        fen_after=game_obj.fen_position
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'fen': game_obj.fen_position,
                        'message': f'Capture failed! {selected_piece} does not exist at {conflict_square}.',
                        'turn': 'white' if game_obj.current_turn else 'black',
                        'quantum_pieces': quantum_pieces_data,
                        'measurement': {
                            'action': 'capture_fails_no_position',
                            'selected_piece': selected_piece,
                            'capture_square': conflict_square
                        }
                    })
                
                # Record measurement in move history
                move_count = Move.objects.filter(game=game_obj).count()
                Move.objects.create(
                    game=game_obj,
                    move_number=move_count // 2 + 1,
                    is_white_move=moving_piece_color == chess.WHITE,
                    move_type='measure',
                    from_square=from_sq,
                    to_square=to_sq,
                    promotion=None,
                    san=f'Measurement at {conflict_square}',
                    fen_after=game_obj.fen_position
                )
                
                game_obj.quantum_pieces = quantum_pieces_data
                game_obj.save()
                
                # Return measurement result - the move may need to be reattempted
                # or may have different outcomes based on measurement
                # For capture_succeeds, continue to normal flow - don't return here
                # The capture will be processed below
        
        # === SCHRÖDINGER'S CAT CHECK ===
        # Check if this is a capture of a quantum piece without conflict
        is_capture = board.is_capture(chess.Move(from_sq, to_sq))
        is_schrodinger = False
        captured_qp = None
        
        if is_capture:
            is_schrodinger, captured_qp = quantum_game.check_schrodinger_capture(
                from_square_name, to_square_name, moving_piece_color
            )
            if is_schrodinger:
                print(f"DEBUG: Schrödinger's cat capture - no measurement needed")
        
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
        
        # === HANDLE CAPTURES ACCORDING TO GAME RULES ===
        
        # If we captured a quantum piece, handle based on whether it was Schrödinger's cat
        if captured_quantum_index is not None and captured_quantum_positions:
            print(f"DEBUG: Capturing quantum piece at {to_square_name}")
            print(f"DEBUG: Quantum piece was at positions: {captured_quantum_positions}")
            
            if is_schrodinger:
                # Schrödinger's cat: capture "half" the quantum piece
                # The piece remains in superposition but loses this state
                print(f"DEBUG: Schrödinger's cat capture - removing captured state only")
                
                # Remove only the captured state from the quantum piece
                qp_data = quantum_pieces_data[captured_quantum_index]
                states_to_remove = []
                for state_id, state_data in list(qp_data.get('qnum', {}).items()):
                    if state_data[0] == to_square_name:
                        states_to_remove.append(state_id)
                
                for state_id in states_to_remove:
                    del qp_data['qnum'][state_id]
                
                # Renormalize probabilities
                remaining_prob = sum(s[1] for s in qp_data['qnum'].values())
                if remaining_prob > 0:
                    for state_data in qp_data['qnum'].values():
                        state_data[1] /= remaining_prob
                
                # The piece is now "half-dead" - in superposition of existing and not existing
                # Game continues with the piece in reduced superposition
                
            else:
                # Regular capture or post-measurement capture
                # The quantum piece collapses to the captured position
                print(f"DEBUG: Regular capture - collapsing quantum piece")
                
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
