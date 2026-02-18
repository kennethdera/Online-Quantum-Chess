"""
Database models for Quantum Chess game.
"""
from django.db import models
from django.contrib.auth.models import User
import json


class Game(models.Model):
    """
    Represents a quantum chess game.
    """
    GAME_STATUS_CHOICES = [
        ('waiting', 'Waiting for Player'),
        ('active', 'Active'),
        ('finished', 'Finished'),
    ]
    
    player_white = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='games_as_white',
        null=True, 
        blank=True
    )
    player_black = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='games_as_black',
        null=True, 
        blank=True
    )
    status = models.CharField(
        max_length=20, 
        choices=GAME_STATUS_CHOICES, 
        default='waiting'
    )
    current_turn = models.BooleanField(default=True)  # True = white, False = black
    fen_position = models.CharField(max_length=100, default='rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')
    quantum_mode = models.BooleanField(default=False)
    move_history = models.JSONField(default=list)
    quantum_pieces = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Game {self.id}: {'White' if self.current_turn else 'Black'}'s turn"


class QuantumPiece(models.Model):
    """
    Represents a quantum piece in superposition or entanglement.
    """
    PIECE_TYPE_CHOICES = [
        ('P', 'Pawn'),
        ('N', 'Knight'),
        ('B', 'Bishop'),
        ('R', 'Rook'),
        ('Q', 'Queen'),
        ('K', 'King'),
    ]
    
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='quantum_pieces_data')
    piece_type = models.CharField(max_length=1, choices=PIECE_TYPE_CHOICES)
    is_white = models.BooleanField()
    quantum_states = models.JSONField(default=dict)  # {state_id: [position, probability]}
    entangled_with = models.JSONField(default=list)  # List of other piece IDs
    is_measured = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{'White' if self.is_white else 'Black'} {self.get_piece_type_display()} in game {self.game.id}"


class Move(models.Model):
    """
    Represents a move in the game.
    """
    MOVE_TYPE_CHOICES = [
        ('normal', 'Normal Move'),
        ('split', 'Split (Quantum)'),
        ('entangle', 'Entangle (Quantum)'),
        ('measure', 'Measurement (Quantum'),
    ]
    
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='moves')
    move_number = models.IntegerField()
    is_white_move = models.BooleanField()
    move_type = models.CharField(max_length=20, choices=MOVE_TYPE_CHOICES, default='normal')
    from_square = models.IntegerField()
    to_square = models.IntegerField()
    promotion = models.CharField(max_length=1, null=True, blank=True)
    san = models.CharField(max_length=10)  # Standard Algebraic Notation
    fen_after = models.CharField(max_length=100)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['move_number', 'is_white_move']
    
    def __str__(self):
        return f"Move {self.move_number}: {'White' if self.is_white_move else 'Black'} - {self.san}"
