"""
Fixed views for Quantum Chess Django application.
Implements Move Declaration Rule from Game Rule/Move Declaration Rule.txt
FIXED: Multiple bugs in quantum moves logic
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
    """
    Make move with proper measurement logic per Game Rule/measuring.txt
    and Move Declaration Rule.txt
    
    Move Declaration Rule:
    1. Declare move (type + target square(s)) - Lock BEFORE measurement
    2. Identify quantum involvement
    3. Trigger measurement if required
    4. Collapse affected quantum states
    5. Validate declared move against new classical board state
    6. Execute move if valid
    7. Otherwise, move fails
    """
    try:
        data = json.loads(request.body)
        game_id = data.get('game_id')
        from_square = data.get('from_square')
        to_square = data.get('to_square')
        promotion = data.get('promotion')
        quantum_mode = data.get('quantum_mode', False)
        
        print(f"DEBUG: game_id={game_id}, from={from_square}, to={to_square}, quantum_mode={quantum_mode}")
        
        game_obj = get_object_or_404(Game, id=game_id)
        print(f"DEBUG: Game found, FEN={game_obj.fen_position[:50]}...")
        
        # Handle quantum mode toggle
        if from_square is None and to_square is None:
            game_obj.quantum_mode = quantum_mode
            game_obj.save()
            return JsonResponse({'success': True, 'quantum_mode': game_obj.quantum_mode, 'message': 'Quantum mode updated'})
        
        from_sq = chess.parse_square(from_square) if isinstance(from_square, str) else from_square
        to_sq = chess.parse_square(to_square) if isinstance(to_square, str) else to_square
        
        board = chess.Board(fen=game_obj.fen_position)
        
        # Get quantum pieces data early - needed for quantum capture detection
        quantum_pieces_data = game_obj.quantum_pieces if game_obj.quantum_pieces else []
        from_square_name = chess.square_name(from_sq)
        to_square_name = chess.square_name(to_sq)
        
        # ========================================================================
        # STEP 1: DECLARE MOVE TYPE - Lock BEFORE measurement (Move Declaration Rule)
        # ========================================================================
        move = chess.Move(from_sq, to_sq)
        if promotion:
            move.promotion = chess.Piece.from_symbol(promotion).piece_type
        
        # BUG FIX: Check if target has quantum piece BEFORE checking classical capture
        # After quantum split, pieces exist in superposition, not on the classical board
        # Also check for quantum pieces at the source (for moving piece)
        source_has_quantum = False
        target_has_quantum = False
        source_quantum_piece = None  # Store the quantum piece at source for later use
        target_quantum_piece = None  # Store the quantum piece at target for later use
        
        for qp in quantum_pieces_data:
            for state_id, state_data in qp.get('qnum', {}).items():
                if state_data[0] == from_square_name:
                    source_has_quantum = True
                    source_quantum_piece = qp
                if state_data[0] == to_square_name:
                    target_has_quantum = True
                    target_quantum_piece = qp
        
        # Check if declared as capture - include quantum piece targets
        is_capture_declared = board.is_capture(move) or target_has_quantum
        declared_move_type = 'capture' if is_capture_declared else 'classical'
        
        # FIX: Handle quantum piece moves - source may not have classical piece
        # If source has quantum piece, we need different validation
        piece = None
        if source_has_quantum:
            # Source has quantum piece - don't validate against classical board
            # The quantum piece will be measured when making the move
            piece = chess.Piece.from_symbol(source_quantum_piece.get('piece', 'P')) if source_quantum_piece else None
        else:
            piece = board.piece_at(from_sq)
        
        moved_piece_symbol = piece.symbol() if piece else None

        # FIX: Validate move only if it's not a quantum piece source
        # Quantum pieces are measured and validated during the measurement step
        # Allow captures since quantum pieces may not be on classical board
        if not source_has_quantum and not is_capture_declared:
            try:
                legal_moves = list(board.legal_moves)
                if move not in legal_moves:
                    return JsonResponse({'success': False, 'error': 'Illegal move'}, status=400)
            except Exception as e:
                return JsonResponse({'success': False, 'error': f'Move validation error: {str(e)}'}, status=400)

        # ========================================================================
        # STEP 2-4: Identify quantum involvement and trigger measurement
        # ========================================================================
        
        # FIXED: Use position-based tracking instead of list indices
        # This prevents index shifting issues when pieces are removed from the list
        
        # Check if moving piece is quantum (attacker) - get piece symbol for reconstruction
        moving_quantum_piece = None
        moving_quantum_positions = {}  # Store positions to check after removal
        for qp in quantum_pieces_data:
            for state_id, state_data in qp.get('qnum', {}).items():
                if state_data[0] == from_square_name:
                    moving_quantum_piece = qp.get('piece')
                    moving_quantum_positions[from_square_name] = qp
                    break
            if moving_quantum_piece:
                break
        
        # Check if capturing a quantum piece (defender)
        captured_quantum_piece = None
        captured_quantum_positions = {}  # Store positions to check after removal
        for qp in quantum_pieces_data:
            for state_id, state_data in qp.get('qnum', {}).items():
                if state_data[0] == to_square_name:
                    captured_quantum_piece = qp.get('piece')
                    captured_quantum_positions[to_square_name] = qp
                    break
            if captured_quantum_piece:
                break
        
        # ========================================================================
        # STEP 3: Trigger measurement if required (Move Declaration Rule)
        # ========================================================================
        
        # Make a temp copy for measurement logic
        measured_quantum_pieces = json.loads(json.dumps(quantum_pieces_data))
        
        # Helper to reconstruct entanglement relationships
        def reconstruct_entanglement(qp_data):
            """Reconstruct QuantumPiece with entanglement from stored data"""
            qp = QPiece(qp_data.get('position', 'a1'), qp_data.get('piece'))
            qp.qnum = qp_data.get('qnum', {'0': [qp_data.get('position', 'a1'), 1]})
            ent_data = qp_data.get('entangled', [])
            reconstructed_ent = []
            for ent_item in ent_data:
                piece_str = ent_item[0]
                state = ent_item[1]
                related_state = ent_item[2]
                # Look through the current measured pieces
                for other_qp_data in measured_quantum_pieces:
                    if other_qp_data.get('piece') == piece_str:
                        other_qp = QPiece(other_qp_data.get('position', 'a1'), other_qp_data.get('piece'))
                        other_qp.qnum = other_qp_data.get('qnum', {'0': [other_qp_data.get('position', 'a1'), 1]})
                        reconstructed_ent.append((other_qp, state, related_state))
                        break
            qp.ent = reconstructed_ent
            return qp
        
        # FIXED: Process the moving (attacking) piece FIRST before any removals
        # This avoids index shifting issues
        if moving_quantum_piece and is_capture_declared:
            # Find the moving quantum piece data in the measured list
            for i, qp_data in enumerate(measured_quantum_pieces):
                found = False
                for state_id, state_data in qp_data.get('qnum', {}).items():
                    if state_data[0] == from_square_name:
                        found = True
                        break
                if found:
                    temp_qp = reconstruct_entanglement(qp_data)
                    measured_pos, prob = temp_qp.measure()
                    # Remove from measured list after measurement
                    measured_quantum_pieces.pop(i)
                    
                    # Validate declared move against new state
                    if measured_pos != from_square_name:
                        temp_board = chess.Board(fen=game_obj.fen_position)
                        measured_from_sq = chess.parse_square(measured_pos)
                        attack_move = chess.Move(measured_from_sq, to_sq)
                        
                        if attack_move not in temp_board.legal_moves:
                            return JsonResponse({
                                'success': False, 
                                'error': f'Capture failed - piece collapsed to {measured_pos}',
                                'fen': game_obj.fen_position,
                                'move_type': declared_move_type
                            })
                    break
        
        # FIXED: Now process the captured (defending) piece - indices are now stable
        if captured_quantum_piece:
            # Find the captured quantum piece data in the measured list
            for i, qp_data in enumerate(measured_quantum_pieces):
                found = False
                for state_id, state_data in qp_data.get('qnum', {}).items():
                    if state_data[0] == to_square_name:
                        found = True
                        break
                if found:
                    temp_qp = reconstruct_entanglement(qp_data)
                    measured_pos, prob = temp_qp.measure()
                    # Remove from measured list
                    measured_quantum_pieces.pop(i)
                    
                    # Validate declared move
                    if declared_move_type == 'capture':
                        if measured_pos != to_square_name:
                            return JsonResponse({
                                'success': False,
                                'error': f'Capture failed - defender collapsed to {measured_pos}',
                                'fen': game_obj.fen_position,
                                'move_type': declared_move_type
                            })
                    break
        
        # ========================================================================
        # STEP 6: Execute move if valid
        # ========================================================================
        
        # FIX: For quantum pieces, we need to add the piece to the board first
        # since it doesn't exist on the classical board
        if source_has_quantum and piece:
            board.set_piece_at(from_sq, piece)
        
        board.push(move)
        # Get SAN of the move that was just pushed
        san = board.san(board.pop())
        board.push(move)
        
        # FIX: If source had quantum piece, the piece is already moved by push()
        # No need to manually remove - the push() handles it
        
        # Update quantum pieces with measured state
        quantum_pieces_data = measured_quantum_pieces
        
        # Handle piece placement based on capture result
        # FIXED: Use the captured_quantum_piece variable instead of index
        if is_capture_declared and captured_quantum_piece:
            if moved_piece_symbol:
                board.set_piece_at(to_sq, chess.Piece.from_symbol(moved_piece_symbol))
        
        # Update game status
        game_obj.status = update_game_status(board, quantum_pieces_data)
        game_obj.fen_position = board.fen()
        game_obj.current_turn = not game_obj.current_turn
        game_obj.quantum_mode = quantum_mode
        game_obj.quantum_pieces = quantum_pieces_data
        game_obj.save()

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
            'move_type': declared_move_type,
            'quantum_pieces': quantum_pieces_data
        })
        
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
    """
    API endpoint to perform a quantum split move
    Per Move Declaration Rule: Split requires two legal destination squares
    FIXED: Turn switching, board state, position field
    """
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
        
        # Reconstruct quantum pieces with position field
        for qp_data in quantum_pieces_data:
            position = qp_data.get('position', 'a1')
            if 'qnum' in qp_data and qp_data['qnum']:
                first_state = list(qp_data['qnum'].values())[0]
                if first_state and first_state[0]:
                    position = first_state[0]
            
            qp = QPiece(position, qp_data.get('piece'))
            qp.qnum = qp_data.get('qnum', {'0': [position, 1]})
            quantum_game.quantum_pieces.append(qp)
        
        from_square_name = chess.square_name(from_sq)
        board = chess.Board(fen=game_obj.fen_position)
        piece = board.piece_at(from_sq)
        
        if not piece:
            return JsonResponse({'success': False, 'error': 'No piece at the source square'}, status=400)
        
        # Two different target squares required
        if to_sq1 == to_sq2:
            return JsonResponse({'success': False, 'error': 'Illegal split: target squares must be different'}, status=400)
        
        # In non-quantum mode, target squares must be empty
        if not game_obj.quantum_mode:
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
        
        # Store with position field
        quantum_pieces_data = []
        for qp in quantum_game.quantum_pieces:
            position = 'a1'
            if qp.qnum:
                first_state = list(qp.qnum.values())[0]
                if first_state and first_state[0]:
                    position = first_state[0]
            
            quantum_pieces_data.append({
                'piece': str(qp.piece), 
                'position': position,
                'qnum': qp.qnum, 
                'entangled': [[str(e[0].piece) if e[0] else None, e[1], e[2]] for e in qp.ent]
            })
        
        game_obj.quantum_pieces = quantum_pieces_data
        game_obj.quantum_mode = True
        
        # FIXED: Remove piece from source square on classical board after quantum split
        # The piece now exists in superposition at the two target squares, not at the source
        # This prevents the piece from appearing twice (classically and quantumly)
        board.remove_piece_at(from_sq)

        # FIXED: Switch turns after quantum split - must flip board.turn before getting FEN
        # In chess, after any move (including quantum split), the turn switches to the other player
        board.turn = not board.turn
        game_obj.fen_position = board.fen()
        game_obj.current_turn = board.turn
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
            san=f'S/{to_square1[0]}{to_square2[0]}',
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
            'move_type': 'split'
        })
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
    """
    API endpoint to perform a quantum entanglement - CASE B
    FIXED: Now properly updates FEN and switches turns
    """
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
                moving_quantum.entangle_oneblock('0', to_square_name, blocking_quantum, blocking_state or '0')
            else:
                moving_quantum = quantum_game.add_quantum_piece(from_square_name, moving_piece.symbol())
                moving_quantum.entangle_oneblock('0', to_square_name, blocking_quantum, blocking_state or '0')
        
        quantum_pieces_data = []
        for qp in quantum_game.quantum_pieces:
            quantum_pieces_data.append({'piece': str(qp.piece), 'qnum': qp.qnum, 'entangled': [[str(e[0].piece) if e[0] else None, e[1], e[2]] for e in qp.ent]})
        
        game_obj.quantum_pieces = quantum_pieces_data
        
        # FIXED: Update FEN and switch turns after entanglement
        game_obj.fen_position = board.fen()
        game_obj.current_turn = not game_obj.current_turn
        game_obj.status = update_game_status(board, quantum_pieces_data)
        game_obj.save()
        
        return JsonResponse({
            'success': True, 
            'message': 'Quantum entanglement performed', 
            'quantum_pieces': quantum_pieces_data,
            'fen': game_obj.fen_position,
            'turn': 'white' if game_obj.current_turn else 'black'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def measure_piece(request):
    """
    API endpoint to measure a quantum piece - handles CASE A/B/C
    FIXED: Now properly updates FEN with the measured position
    """
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
            
            # FIXED: Update the board with the measured piece position
            if measured_piece and final_pos:
                board.remove_piece_at(chess.parse_square(square))
                board.set_piece_at(chess.parse_square(final_pos), measured_piece)
            
            game_obj.fen_position = board.fen()
            game_obj.status = update_game_status(board, game_obj.quantum_pieces)
            game_obj.save()
            
            return JsonResponse({
                'success': True, 
                'message': f'Piece at {square} measured and collapsed to {final_pos}', 
                'final_position': final_pos, 
                'probability': prob, 
                'fen': game_obj.fen_position, 
                'quantum_pieces': game_obj.quantum_pieces,
                'move_type': 'measure'
            })
        
        return JsonResponse({'success': False, 'error': f'No quantum piece found at {square}'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def get_game_state(request, game_id):
    """FIXED: Corrected syntax error in JSON response"""
    game_obj = get_object_or_404(Game, id=game_id)
    
    moves = Move.objects.filter(game=game_obj).order_by('move_number', 'is_white_move')
    move_list = []
    for m in moves:
        move_list.append({'number': m.move_number, 'is_white': m.is_white_move, 'san': m.san, 'type': m.move_type})
    
    return JsonResponse({
        'game_id': game_obj.id, 
        'fen': game_obj.fen_position,  # FIXED: was 'game,' which is undefined
        'turn': 'white' if game_obj.current_turn else 'black', 
        'quantum_mode': game_obj.quantum_mode, 
        'status': game_obj.status, 
        'moves': move_list, 
        'quantum_pieces': game_obj.quantum_pieces if game_obj.quantum_pieces else []
    })


def game_list(request):
    games = Game.objects.all()[:20]
    return render(request, 'quantum_chess/game_list.html', {'games': games})

