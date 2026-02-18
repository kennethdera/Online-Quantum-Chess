"""
Serializers for Quantum Chess API.

This module contains serializers for converting Django models to JSON.
"""

from rest_framework import serializers
from .models import Game, Move, QuantumPiece


class QuantumPieceSerializer(serializers.ModelSerializer):
    """
    Serializer for QuantumPiece model.
    """
    class Meta:
        model = QuantumPiece
        fields = ['id', 'piece_type', 'is_white', 'quantum_states', 
                  'entangled_with', 'is_measured']


class MoveSerializer(serializers.ModelSerializer):
    """
    Serializer for Move model.
    """
    class Meta:
        model = Move
        fields = ['id', 'move_number', 'is_white_move', 'move_type',
                  'from_square', 'to_square', 'promotion', 'san', 
                  'fen_after', 'timestamp']


class GameSerializer(serializers.ModelSerializer):
    """
    Serializer for Game model.
    """
    moves = MoveSerializer(many=True, read_only=True)
    quantum_pieces = QuantumPieceSerializer(many=True, read_only=True)
    
    class Meta:
        model = Game
        fields = ['id', 'player_white', 'player_black', 'status', 
                  'current_turn', 'fen_position', 'quantum_mode',
                  'move_history', 'quantum_pieces', 'created_at', 
                  'updated_at', 'moves', 'quantum_pieces_data']
