# coding = utf-8
# author = fufu

import sqlite3
import os
from pathlib import Path

project_root = Path(__file__).parent.parent
instance_dir = project_root / "instance"
instance_dir.mkdir(exist_ok=True)
db_path = instance_dir / "orders.db"

def get_db_connection():
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():


    with get_db_connection() as conn:
        #1 用户表uers
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                phone TEXT UNIQUE,          
                email TEXT UNIQUE,          
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("insert or ignore into users (username, password,created_at) values ('tester', 'SecurePass123!','2025-09-12 10:11:42.556733')")
        conn.execute("insert or ignore into users (username, password,created_at) values ('admin', 'AdminPass456!','2025-09-12 10:21:42.556733')")
        # 2 账户余额表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS accounts  (
            username TEXT PRIMARY KEY,
            balance REAL NOT NULL,
            FOREIGN KEY (username) REFERENCES users (username)
            )    
        """)
        conn.execute("""
            INSERT OR IGNORE  INTO accounts (username, balance) VALUES ('tester', '2000')
        """)
        conn.execute("""
            INSERT OR IGNORE  INTO accounts (username, balance) VALUES ('admin', '5000')
        """)
        # 3 交易流水表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            type TEXT NOT NULL,          -- DEPOSIT, WITHDRAW, PAYMENT
            amount REAL NOT NULL,
            time TEXT NOT NULL,
            FOREIGN KEY(username) REFERENCES users(username)
            )
        """)
        conn.execute('''
                   INSERT OR IGNORE INTO transactions (id, username, type, amount, time)
                   VALUES ('txn_t001', 'tester', 'DEPOSIT', 1000.0, '2025-09-13 10:21:42.556733')
               ''')
        conn.execute('''
                           INSERT OR IGNORE INTO transactions (id, username, type, amount, time)
                           VALUES ('txn_t002', 'tester', 'DEPOSIT', 1000.0, '2025-09-14 10:21:42.556733')
                       ''')
        conn.execute('''
                    INSERT OR IGNORE INTO transactions (id, username, type, amount, time)
                    VALUES ('txn_a001', 'admin', 'DEPOSIT', 5000.0, '2025-09-13 10:21:42.556733')
                ''')
        # 4. 订单表
        conn.execute('''
                    CREATE TABLE IF NOT EXISTS orders (
                        order_id TEXT PRIMARY KEY,
                        username TEXT NOT NULL,
                        amount REAL NOT NULL,
                        currency TEXT NOT NULL CHECK (currency IN ('CNY', 'USD')),
                        order_type TEXT NOT NULL,
                        product_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(username) REFERENCES users(username)
                    )
                ''')
        # 5. 上传文件表
        conn.execute('''
                    CREATE TABLE IF NOT EXISTS uploads (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        filename TEXT NOT NULL,
                        original_name TEXT NOT NULL,
                        file_size INTEGER NOT NULL,
                        username TEXT NOT NULL,
                        upload_time TEXT NOT NULL,
                        FOREIGN KEY(username) REFERENCES users(username)
                    )
                ''')
        #6 token
        conn.execute('''
                    CREATE TABLE IF NOT EXISTS tokens (
                        token TEXT PRIMARY KEY,
                        username TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL
                    )
                ''')
        # api_keys
        conn.execute('''
                    CREATE TABLE IF NOT EXISTS api_keys (
                        key_id TEXT PRIMARY KEY,
                        secret TEXT NOT NULL,
                        username TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        is_active BOOLEAN DEFAULT 1,
                        FOREIGN KEY(username) REFERENCES users(username) 
                    )
                ''')
        conn.execute(
            "insert or ignore into api_keys (key_id, secret, username, created_at) VALUES ('abc123', 'SuperSecretKey456!', 'tester', '2025-09-12 10:11:42.556733')")
        # =============== 新增：挂单、购买、审核相关表 ===============

        # 8. 挂单表（卖家发布）
        conn.execute('''
                    CREATE TABLE IF NOT EXISTS listings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        seller_username TEXT NOT NULL,
                        product_id TEXT NOT NULL,
                        amount REAL NOT NULL,
                        currency TEXT NOT NULL CHECK (currency IN ('CNY', 'USD')),
                        status TEXT DEFAULT 'LISTED' CHECK (status IN ('LISTED', 'SOLD', 'CANCELLED')),
                        created_at TEXT NOT NULL,
                        sold_at TEXT,
                        FOREIGN KEY(seller_username) REFERENCES users(username)
                    )
                ''')


        # 9. 购买订单表（买家对挂单的购买请求）
        conn.execute('''
                    CREATE TABLE IF NOT EXISTS purchase_orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        listing_id INTEGER NOT NULL,
                        buyer_username TEXT NOT NULL,
                        amount REAL NOT NULL,          -- 应等于 listing.amount
                        currency TEXT NOT NULL,
                        status TEXT DEFAULT 'PENDING_REVIEW' CHECK (status IN ('PENDING_REVIEW', 'COMPLETED', 'REJECTED', 'CANCELLED')),
                        created_at TEXT NOT NULL,
                        reviewed_at TEXT,
                        reviewed_by TEXT,              -- 审核人（通常是 admin）
                        review_action TEXT,            -- 'approve' / 'reject'
                        FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE,
                        FOREIGN KEY(buyer_username) REFERENCES users(username)
                    )
                ''')

        # 10. （可选）后台管理员角色标记 —— 这里我们不单独建表，而是通过用户名判断（如 'admin'）
        #     如果未来需要多管理员，可建 admin_users 表，但目前用 'admin' 用户即可

        conn.execute('''CREATE TABLE IF NOT EXISTS admins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL
        )''')
        # 可选：插入一条测试挂单（用于接口调试）
        conn.execute('''
            INSERT OR IGNORE INTO admins (username,password,role) VALUES (?,?,?)
        ''', ('HOUTAIMIN', '123A',"ADMIN"))
        conn.execute('''
                    INSERT OR IGNORE INTO admins (username,password,role) VALUES (?,?,?)
                ''', ('XIXI', '123AA', "NORMAL"))

        conn.commit()







