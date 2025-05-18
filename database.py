import asyncpg
import os

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(dsn=os.getenv("DATABASE_URL"))
        await self.ensure_primary_key()
        await self.ensure_lister_key()

    async def ensure_primary_key(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.table_constraints
                        WHERE table_name = 'registreringer' AND constraint_type = 'PRIMARY KEY'
                    ) THEN
                        ALTER TABLE registreringer
                        ADD PRIMARY KEY (guild_id, listename, user_id, charname);
                    END IF;
                END
                $$;
            """)

    async def ensure_lister_key(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.table_constraints
                        WHERE table_name = 'lister' AND constraint_type = 'PRIMARY KEY'
                    ) THEN
                        ALTER TABLE lister
                        ADD PRIMARY KEY (guild_id, listename);
                    END IF;
                END
                $$;
            """)

    async def add_registrering(self, guild_id, listename, user_id, charname, spec, class_, ilvl, rio, rolle):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO registreringer (guild_id, listename, user_id, charname, spec, class, ilvl, rio, rolle)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT (guild_id, listename, user_id, charname)
                DO UPDATE SET spec=$5, class=$6, ilvl=$7, rio=$8, rolle=$9
            """, guild_id, listename, user_id, charname, spec, class_, ilvl, rio, rolle)

    async def fjern_registrering(self, guild_id, listename, user_id, charname=None):
        async with self.pool.acquire() as conn:
            if charname:
                await conn.execute("""
                    DELETE FROM registreringer
                    WHERE guild_id=$1 AND listename=$2 AND user_id=$3 AND charname=$4
                """, guild_id, listename, user_id, charname)
            else:
                await conn.execute("""
                    DELETE FROM registreringer
                    WHERE guild_id=$1 AND listename=$2 AND user_id=$3
                """, guild_id, listename, user_id)

    async def hent_alle(self, guild_id, listename):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT * FROM registreringer
                WHERE guild_id=$1 AND listename=$2
                ORDER BY rolle, charname
            """, guild_id, listename)

    async def get_liste(self, guild_id, listename):
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT * FROM lister
                WHERE guild_id=$1 AND listename=$2
            """, guild_id, listename)
            return dict(result) if result else None

    async def opret_liste(self, guild_id, listename, titel, besked_id, ejer_id):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO lister (guild_id, listename, titel, besked_id, ejer_id)
                VALUES ($1,$2,$3,$4,$5)
                ON CONFLICT (guild_id, listename)
                DO UPDATE SET titel=$3, besked_id=$4, ejer_id=$5
            """, guild_id, listename, titel, besked_id, ejer_id)

    async def slet_liste(self, guild_id, listename):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM lister
                WHERE guild_id=$1 AND listename=$2
            """, guild_id, listename)

    async def opdater_besked_id(self, guild_id, listename, besked_id):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE lister
                SET besked_id=$3
                WHERE guild_id=$1 AND listename=$2
            """, guild_id, listename, besked_id)