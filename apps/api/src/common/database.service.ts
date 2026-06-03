import { Injectable, OnModuleDestroy } from '@nestjs/common';
import { Pool, QueryResultRow } from 'pg';

@Injectable()
export class DatabaseService implements OnModuleDestroy {
  private pool = new Pool({ connectionString: process.env.DATABASE_URL });

  query<T extends QueryResultRow = any>(sql: string, params: any[] = []) {
    return this.pool.query<T>(sql, params);
  }

  async onModuleDestroy() {
    await this.pool.end();
  }
}
