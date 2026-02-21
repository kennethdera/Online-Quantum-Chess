"""
URL configuration for quantum_chess app.
"""
from django.urls import path
from . import views

app_name = 'quantum_chess'

urlpatterns = [
    path('', views.index, name='index'),
    path('game/<int:game_id>/', views.game, name='game'),
    path('new/', views.new_game, name='new_game'),
    path('game/<int:game_id>/state/', views.get_game_state, name='game_state'),
    path('move/', views.make_move, name='make_move'),
    path('quantum/toggle/', views.toggle_quantum_mode, name='toggle_quantum_mode'),
    path('quantum/split/', views.quantum_split, name='quantum_split'),
    path('quantum/entangle/', views.quantum_entangle, name='quantum_entangle'),

    path('quantum/measure/', views.measure_piece, name='measure_piece'),
    path('games/', views.game_list, name='game_list'),
]
