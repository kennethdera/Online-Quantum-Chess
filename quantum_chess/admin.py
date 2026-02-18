"""
Admin configuration for Quantum Chess models.
"""

from django.contrib import admin
from .models import Game, Move, QuantumPiece


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ['id', 'status', 'current_turn', 'quantum_mode', 'created_at']
    list_filter = ['status', 'current_turn', 'quantum_mode', 'created_at']
    search_fields = ['id', 'fen_position']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Move)
class MoveAdmin(admin.ModelAdmin):
    list_display = ['id', 'game', 'move_number', 'is_white_move', 'move_type', 'san']
    list_filter = ['is_white_move', 'move_type']
    search_fields = ['san', 'game__id']


@admin.register(QuantumPiece)
class QuantumPieceAdmin(admin.ModelAdmin):
    list_display = ['id', 'game', 'piece_type', 'is_white', 'is_measured']
    list_filter = ['piece_type', 'is_white', 'is_measured']
