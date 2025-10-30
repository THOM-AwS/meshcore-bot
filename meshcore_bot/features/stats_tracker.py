#!/usr/bin/env python3
"""
Simple stats tracking for Jeff - tracks messages, commands, and paths
"""

import sqlite3
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger('meshcore.bot')


class StatsTracker:
    """Lightweight stats tracking without full database manager overhead"""

    def __init__(self, db_path: str = '/var/tmp/jeff_stats.db'):
        self.db_path = db_path
        self._init_tables()

    def _init_tables(self):
        """Initialize stats tables"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Message stats - all messages seen
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS message_stats (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp INTEGER NOT NULL,
                        sender_id TEXT NOT NULL,
                        channel TEXT,
                        is_dm BOOLEAN NOT NULL,
                        hops INTEGER,
                        snr REAL,
                        rssi INTEGER,
                        path TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Command stats - bot commands executed
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS command_stats (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp INTEGER NOT NULL,
                        sender_id TEXT NOT NULL,
                        command_name TEXT NOT NULL,
                        channel TEXT,
                        is_dm BOOLEAN NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Path stats - interesting paths
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS path_stats (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp INTEGER NOT NULL,
                        sender_id TEXT NOT NULL,
                        channel TEXT,
                        path_length INTEGER NOT NULL,
                        path_string TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Indexes for performance
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_msg_time ON message_stats(timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_cmd_time ON command_stats(timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_path_time ON path_stats(timestamp)')

                conn.commit()
                logger.info(f"Stats tables initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize stats tables: {e}")
            raise

    def record_message(self, sender_id: str, channel: str, is_dm: bool,
                       hops: int = None, snr: float = None, rssi: int = None, path: str = None):
        """Record a message"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO message_stats (timestamp, sender_id, channel, is_dm, hops, snr, rssi, path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (int(time.time()), sender_id, channel, is_dm, hops, snr, rssi, path))
                conn.commit()
        except Exception as e:
            logger.debug(f"Error recording message stats: {e}")

    def record_command(self, sender_id: str, command_name: str, channel: str, is_dm: bool):
        """Record a command execution"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO command_stats (timestamp, sender_id, command_name, channel, is_dm)
                    VALUES (?, ?, ?, ?, ?)
                ''', (int(time.time()), sender_id, command_name, channel, is_dm))
                conn.commit()
        except Exception as e:
            logger.debug(f"Error recording command stats: {e}")

    def record_path(self, sender_id: str, channel: str, path_length: int, path_string: str):
        """Record an interesting path (3+ hops)"""
        if path_length >= 3:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO path_stats (timestamp, sender_id, channel, path_length, path_string)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (int(time.time()), sender_id, channel, path_length, path_string))
                    conn.commit()
            except Exception as e:
                logger.debug(f"Error recording path stats: {e}")

    def get_stats_24h(self) -> Dict:
        """Get 24-hour statistics"""
        try:
            cutoff = int(time.time()) - (24 * 60 * 60)

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Total messages
                cursor.execute('SELECT COUNT(*) FROM message_stats WHERE timestamp >= ?', (cutoff,))
                total_messages = cursor.fetchone()[0]

                # Total commands
                cursor.execute('SELECT COUNT(*) FROM command_stats WHERE timestamp >= ?', (cutoff,))
                total_commands = cursor.fetchone()[0]

                # Top command
                cursor.execute('''
                    SELECT command_name, COUNT(*) as count
                    FROM command_stats
                    WHERE timestamp >= ?
                    GROUP BY command_name
                    ORDER BY count DESC
                    LIMIT 1
                ''', (cutoff,))
                top_cmd = cursor.fetchone()
                top_command = f"{top_cmd[0]}({top_cmd[1]})" if top_cmd else "None"

                # Top user
                cursor.execute('''
                    SELECT sender_id, COUNT(*) as count
                    FROM command_stats
                    WHERE timestamp >= ?
                    GROUP BY sender_id
                    ORDER BY count DESC
                    LIMIT 1
                ''', (cutoff,))
                top_usr = cursor.fetchone()
                top_user = f"{top_usr[0][:15]}({top_usr[1]})" if top_usr else "None"

                return {
                    'messages': total_messages,
                    'commands': total_commands,
                    'top_command': top_command,
                    'top_user': top_user
                }
        except Exception as e:
            logger.error(f"Error getting 24h stats: {e}")
            return {'messages': 0, 'commands': 0, 'top_command': 'Error', 'top_user': 'Error'}

    def get_channel_stats_24h(self) -> List[tuple]:
        """Get channel activity for 24h"""
        try:
            cutoff = int(time.time()) - (24 * 60 * 60)

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT channel, COUNT(*) as msg_count, COUNT(DISTINCT sender_id) as unique_users
                    FROM message_stats
                    WHERE timestamp >= ? AND channel IS NOT NULL
                    GROUP BY channel
                    ORDER BY msg_count DESC
                    LIMIT 5
                ''', (cutoff,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting channel stats: {e}")
            return []

    def get_path_stats_24h(self) -> List[tuple]:
        """Get longest paths for 24h"""
        try:
            cutoff = int(time.time()) - (24 * 60 * 60)

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT sender_id, path_length, path_string
                    FROM path_stats
                    WHERE timestamp >= ?
                    ORDER BY path_length DESC
                    LIMIT 5
                ''', (cutoff,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting path stats: {e}")
            return []

    def cleanup_old_stats(self, days_to_keep: int = 7):
        """Clean up stats older than N days"""
        try:
            cutoff = int(time.time()) - (days_to_keep * 24 * 60 * 60)

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM message_stats WHERE timestamp < ?', (cutoff,))
                msg_deleted = cursor.rowcount
                cursor.execute('DELETE FROM command_stats WHERE timestamp < ?', (cutoff,))
                cmd_deleted = cursor.rowcount
                cursor.execute('DELETE FROM path_stats WHERE timestamp < ?', (cutoff,))
                path_deleted = cursor.rowcount
                conn.commit()

                total = msg_deleted + cmd_deleted + path_deleted
                if total > 0:
                    logger.info(f"Cleaned up {total} old stats entries")
        except Exception as e:
            logger.error(f"Error cleaning up stats: {e}")
