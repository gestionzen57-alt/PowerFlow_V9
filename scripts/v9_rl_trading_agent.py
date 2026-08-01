"""v9_rl_trading_agent.py — Phase 92 motion CEO 48H (post-Plan C).

RL trading agent simplifié (Q-learning, sans PPO complet).
State : 10 features marché. Actions : HOLD(0)/LONG(1)/SHORT(2).

Auteur : Hermes (Phase 92 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import logging
import random
from collections import defaultdict
from typing import Any

log = logging.getLogger("v9.rl_agent")


class TradingAgent:
    """Q-learning agent pour trading discret.

    Action space : 0=HOLD, 1=LONG, 2=SHORT.
    State space : vecteur de 10 features (compatible multi-TF).
    """

    def __init__(
        self,
        state_dim: int = 10,
        n_actions: int = 3,
        epsilon: float = 0.10,
        alpha: float = 0.10,
        gamma: float = 0.95,
    ) -> None:
        self.state_dim = state_dim
        self.n_actions = n_actions
        self.epsilon = epsilon
        self.alpha = alpha
        self.gamma = gamma
        self.q_table: dict[tuple, float] = defaultdict(float)

    def _state_key(self, state: list[float]) -> tuple:
        """Discretise le state en tuple de 3 categories par feature.

        Pour test : utilise state[0..2] ou tout si state_dim < 3.
        """
        # Discretisation simple : arrondir ou binariser
        if len(state) >= 3:
            return (
                int(state[0] * 10) % 10,
                int(state[1] * 10) % 10,
                int(state[2] * 10) % 10,
            )
        return tuple(int(s * 10) % 10 for s in state)

    def select_action(self, state: list[float]) -> int:
        """Epsilon-greedy policy."""
        if random.random() < self.epsilon:
            return random.randint(0, self.n_actions - 1)
        # Greedy
        state_key = self._state_key(state)
        q_values = [
            self.q_table[(state_key[0], state_key[1], state_key[2], a)]
            for a in range(self.n_actions)
        ]
        # Si toutes 0, choisir aleatoire
        if all(q == 0 for q in q_values):
            return random.randint(0, self.n_actions - 1)
        return q_values.index(max(q_values))

    def update_q_value(
        self, state: list[float], action: int,
        reward: float, next_state: list[float],
    ) -> None:
        """Update Q-value via Bellman equation."""
        sk = self._state_key(state)
        nsk = self._state_key(next_state)
        current_q = self.q_table[(sk[0], sk[1], sk[2], action)]
        # Max Q sur next_state
        next_q_max = max(
            self.q_table[(nsk[0], nsk[1], nsk[2], a)]
            for a in range(self.n_actions)
        )
        new_q = current_q + self.alpha * (
            reward + self.gamma * next_q_max - current_q
        )
        self.q_table[(sk[0], sk[1], sk[2], action)] = new_q


def compute_reward(pnl: float, dd: float = 0.0) -> float:
    """Reward = pnl - dd * 0.1 (penalite drawdown)."""
    return pnl - abs(dd) * 0.1


class SimpleTradingEnv:
    """Environnement trading minimal pour tests RL."""

    def __init__(self, n_steps: int = 100, state_dim: int = 4) -> None:
        self.n_steps = n_steps
        self.state_dim = state_dim
        self.t = 0
        self.rng = random.Random(42)

    def reset(self) -> list[float]:
        self.t = 0
        return [self.rng.random() for _ in range(self.state_dim)]

    def step(self, action: int) -> tuple[list[float], float, bool]:
        """Action 0=HOLD, 1=LONG, 2=SHORT."""
        self.t += 1
        # Reward base sur action
        base = self.rng.uniform(-10, 30)
        if action == 0:  # HOLD
            r = 0.0
        elif action == 1:  # LONG
            r = base
        else:  # SHORT
            r = -base
        next_state = [self.rng.random() for _ in range(self.state_dim)]
        done = self.t >= self.n_steps
        return next_state, r, done


def simple_trading_env(n_steps: int = 100) -> SimpleTradingEnv:
    """Factory."""
    return SimpleTradingEnv(n_steps=n_steps)


def train_episode(agent: TradingAgent, env: SimpleTradingEnv) -> float:
    """Execute un episode d'entrainement. Retourne reward total."""
    state = env.reset()
    total_reward = 0.0
    done = False
    while not done:
        action = agent.select_action(state)
        next_state, reward, done = env.step(action)
        agent.update_q_value(state, action, reward, next_state)
        total_reward += reward
        state = next_state
    return total_reward


def main(argv=None) -> int:
    """Demo RL agent sur env simple."""
    print("=" * 70)
    print("V9 RL TRADING AGENT (Phase 92)")
    print("=" * 70)
    agent = TradingAgent(state_dim=4, n_actions=3, epsilon=0.20)
    env = simple_trading_env(n_steps=100)
    rewards = []
    for ep in range(20):
        # Reset epsilon au fur et a mesure (decay)
        agent.epsilon = max(0.05, agent.epsilon * 0.95)
        total = train_episode(agent, env)
        rewards.append(total)
    print(f"Episodes       : {len(rewards)}")
    print(f"Reward moyen   : {sum(rewards)/len(rewards):.2f}")
    print(f"Reward max     : {max(rewards):.2f}")
    print(f"Reward min     : {min(rewards):.2f}")
    print(f"Q-table size   : {len(agent.q_table)}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    sys.exit(main())