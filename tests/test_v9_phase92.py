"""tests/test_v9_phase92.py — Phase 92 motion CEO 48H (post-Plan C).

Tests pour rl_trading_agent.
"""
import pytest


def test_agent_creation():
    from scripts.v9_rl_trading_agent import TradingAgent
    agent = TradingAgent(state_dim=10, n_actions=3)
    assert agent.state_dim == 10
    assert agent.n_actions == 3


def test_agent_default():
    from scripts.v9_rl_trading_agent import TradingAgent
    agent = TradingAgent()
    assert agent.state_dim == 10
    assert agent.n_actions == 3


def test_select_action_returns_valid():
    from scripts.v9_rl_trading_agent import TradingAgent
    agent = TradingAgent(state_dim=5, n_actions=3)
    state = [0.1, 0.2, 0.3, 0.4, 0.5]
    action = agent.select_action(state)
    assert action in (0, 1, 2)


def test_select_action_epsilon_exploration():
    """En mode explore, l'action peut etre aleatoire."""
    from scripts.v9_rl_trading_agent import TradingAgent
    agent = TradingAgent(state_dim=5, n_actions=3, epsilon=0.99)
    state = [0.1] * 5
    # Avec epsilon=0.99, l'action devrait souvent etre aleatoire
    actions_seen = set()
    for _ in range(20):
        a = agent.select_action(state)
        actions_seen.add(a)
    # Au moins 2 actions differentes sur 20 essais
    assert len(actions_seen) >= 2


def test_compute_reward_positive():
    """Reward positif pour trade gagnant."""
    from scripts.v9_rl_trading_agent import compute_reward
    r = compute_reward(pnl=25.0, dd=-5.0)
    assert r > 0


def test_compute_reward_negative():
    """Reward negatif pour trade perdant."""
    from scripts.v9_rl_trading_agent import compute_reward
    r = compute_reward(pnl=-8.0, dd=-5.0)
    assert r < 0


def test_compute_reward_penalty_dd():
    """DD ajoute une penalite."""
    from scripts.v9_rl_trading_agent import compute_reward
    r_low_dd = compute_reward(pnl=10.0, dd=-5.0)
    r_high_dd = compute_reward(pnl=10.0, dd=-30.0)
    assert r_low_dd > r_high_dd


def test_update_q_value():
    from scripts.v9_rl_trading_agent import TradingAgent
    agent = TradingAgent(state_dim=3, n_actions=2, alpha=0.5, gamma=0.9)
    # _state_key discretise state[0..2] en int(s*10)%10.
    # state=[1.5, 1.5, 1.5] → (5, 5, 5)
    initial_q = agent.q_table.get((5, 5, 5, 0), 0.0)
    assert initial_q == 0.0
    agent.update_q_value(
        state=[1.5, 1.5, 1.5], action=0,
        reward=1.0, next_state=[1.5, 1.5, 1.5],
    )
    new_q = agent.q_table.get((5, 5, 5, 0), 0.0)
    assert new_q != initial_q
    assert new_q > 0  # reward=1.0 a update Q vers le haut


def test_train_episode_returns_total_reward():
    from scripts.v9_rl_trading_agent import (
        TradingAgent, simple_trading_env, train_episode,
    )
    agent = TradingAgent(state_dim=4, n_actions=3, epsilon=0.5)
    env = simple_trading_env(n_steps=20)
    total = train_episode(agent, env)
    assert isinstance(total, (int, float))


def test_simple_env_runs():
    from scripts.v9_rl_trading_agent import simple_trading_env
    env = simple_trading_env(n_steps=10)
    state = env.reset()
    assert len(state) == 4  # state_dim=4
    next_state, reward, done = env.step(0)
    assert len(next_state) == 4


def test_simple_env_done():
    from scripts.v9_rl_trading_agent import simple_trading_env
    env = simple_trading_env(n_steps=5)
    env.reset()
    done = False
    for _ in range(10):
        _, _, d = env.step(0)
        if d:
            done = True
            break
    assert done is True


def test_main_demo(capsys):
    from scripts.v9_rl_trading_agent import main
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "RL TRADING AGENT" in captured.out