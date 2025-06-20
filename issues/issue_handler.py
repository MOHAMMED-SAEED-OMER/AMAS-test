# issues/issue_handler.py
import pandas as pd
from datetime import datetime
from db_handler import DatabaseManager


class IssueHandler(DatabaseManager):
    """CRUD helpers for the *issues* table."""

    # ────────────────────────── CREATE ──────────────────────────
    def add_issue(
        self,
        reported_by: str,
        category: str,
        location: str | None,
        description: str,
        photo_bytes: bytes | None = None,
    ) -> int:
        """
        Insert a new issue and return the new primary-key (issueid).
        """
        sql = """
        INSERT INTO issues
              (reported_by, category, location, description, photo)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING issueid
        """
        res = self.execute_command_returning(
            sql,
            (reported_by, category, location, description, photo_bytes),
        )
        return int(res[0])

    # ─────────────────────────── READ ───────────────────────────
    def fetch_issues(
        self,
        status: str | None = None,          # e.g. "Open", "Solved"
        include_closed: bool = False,       # keep for flexibility
    ) -> pd.DataFrame:
        """
        Return issues filtered by status.  
        • `status=None`  → all issues (optionally excluding "Closed")  
        • `status="Open"`→ only open issues, etc.
        """
        sql     = "SELECT * FROM issues"
        params  = []

        clauses = []
        if status:
            clauses.append("status = %s")
            params.append(status)
        elif not include_closed:
            clauses.append("status <> 'Closed'")

        if clauses:
            sql += " WHERE " + " AND ".join(clauses)

        sql += " ORDER BY created_at DESC"
        return self.fetch_data(sql, tuple(params))

    # ────────────────────────── UPDATE ──────────────────────────
    def update_issue_status(
        self,
        issue_id:      int,
        new_status:    str,
        solved_by:     str,
        solved_at,                 # datetime
        solved_note:   str | None = None,
        solved_photo:  bytes | None = None,   # ★ NEW
    ) -> None:
        """
        Mark an issue Solved / Closed and attach optional
        note + photo evidence.
        """
        sql = """
        UPDATE issues
           SET status        = %s,
               solved_by     = %s,
               solved_at     = %s,
               solved_note   = %s,
               solved_photo  = %s
         WHERE issueid       = %s
        """
        self.execute_command(
            sql,
            (new_status, solved_by, solved_at, solved_note, solved_photo, issue_id)
        )

    # (Optional) helper that just flips status without note
    def set_status(
        self,
        issue_id: int,
        new_status: str,
        resolver: str | None = None,
    ) -> None:
        """
        Simple status change utility. If closing, records resolver & timestamp.
        """
        if new_status == "Closed":
            sql = """
            UPDATE issues
               SET status      = 'Closed',
                   solved_by   = %s,
                   solved_at   = CURRENT_TIMESTAMP
             WHERE issueid = %s
            """
            self.execute_command(sql, (resolver, issue_id))
        else:
            self.execute_command(
                "UPDATE issues SET status = %s WHERE issueid = %s",
                (new_status, issue_id),
            )
