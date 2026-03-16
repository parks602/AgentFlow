import sqlite3
import json
from datetime import datetime


class AgentMemory:
    """
    SQLite 기반 에이전트 메모리
    각 에이전트의 과거 결정 이력을 저장하고 조회
    다음 결정 시 컨텍스트로 활용
    """

    def __init__(self, db_path: str = "simulation.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    simulation_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    round INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT,
                    confidence REAL,
                    market_context TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def save(
        self,
        simulation_id: str,
        agent_id: str,
        round_num: int,
        decision: dict,
        market_context: str = "",
    ):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO agent_decisions
                (simulation_id, agent_id, round, action, reason, confidence, market_context)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    simulation_id,
                    agent_id,
                    round_num,
                    decision.get("action", "관망"),
                    decision.get("reason", ""),
                    decision.get("confidence", 0.5),
                    market_context[:500],
                ),
            )
            conn.commit()

    def get_recent(self, agent_id: str, n: int = 3) -> list[dict]:
        """해당 에이전트의 최근 N개 결정 이력 조회"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT simulation_id, action, reason, confidence, created_at
                FROM agent_decisions
                WHERE agent_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (agent_id, n),
            )
            rows = cursor.fetchall()

        return [
            {"simulation_id": r[0], "action": r[1], "reason": r[2], "confidence": r[3], "date": r[4]}
            for r in rows
        ]

    def get_all_decisions(self, simulation_id: str) -> list[dict]:
        """시뮬레이션 전체 결정 이력 조회 (대시보드용)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT agent_id, round, action, reason, confidence, created_at
                FROM agent_decisions
                WHERE simulation_id = ?
                ORDER BY round, agent_id
                """,
                (simulation_id,),
            )
            rows = cursor.fetchall()

        return [
            {
                "agent_id": r[0],
                "round": r[1],
                "action": r[2],
                "reason": r[3],
                "confidence": r[4],
                "created_at": r[5],
            }
            for r in rows
        ]

    def clear_simulation(self, simulation_id: str):
        """특정 시뮬레이션 데이터 초기화"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM agent_decisions WHERE simulation_id = ?",
                (simulation_id,),
            )
            conn.commit()

    def clear_all_agent_history(self):
        """에이전트 전체 결정 이력 초기화 — 종목 전환 시 교차 오염 방지"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM agent_decisions")
            conn.commit()
        print("[Memory] 에이전트 결정 이력 초기화 완료")