"""Reproducible offline benchmark: python -m tests.benchmark_brain.

Numbers describe this interpreter/workspace, not production or model throughput.
No tokens, Discord connections, embedding services, or model downloads required.
"""
from __future__ import annotations

import asyncio
import json
import platform
import resource
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path
from types import SimpleNamespace

from services.ai_engine.config import BrainConfig
from services.ai_engine.engine import AIEngine
from services.ai_engine.memory import AIMemoryService
from services.ai_engine.models import AIRequest
from services.ai_engine.rag import RAGStore
from services.ai_engine.router import RequestRouter
from services.ai_engine.tools import ToolContext


def summary(values):
    return {'n':len(values), 'median_ms':round(statistics.median(values), 4),
            'p95_ms':round(sorted(values)[max(0, int(len(values)*.95)-1)], 4)}


async def main():
    # Sample small operations without tracing overhead for comparable timing.
    route=[]
    for _ in range(2000):
        started=time.perf_counter()
        RequestRouter.route('can you explain Python asyncio?')
        route.append((time.perf_counter()-started)*1000)
    with tempfile.TemporaryDirectory() as tmp:
        memory=AIMemoryService(db_path=Path(tmp)/'benchmark.sqlite3')
        await memory.initialize()
        await memory.remember(1,2,'language','Hinglish')
        lookups=[]
        for _ in range(100):
            started=time.perf_counter()
            await memory.memories(1,2)
            lookups.append((time.perf_counter()-started)*1000)
        # Share the same AI database, as production does.
        rag=RAGStore(db_path=memory.db_path)
        for index in range(100):
            await rag.add(f'Python guide {index}', f'Python asyncio task queue guide item {index}',
                          source_type='local', embed=False)
        retrieval=[]
        for _ in range(25):
            started=time.perf_counter()
            await rag.search('Python asyncio task queue', embed=False)
            retrieval.append((time.perf_counter()-started)*1000)
        engine=AIEngine(config=BrainConfig(external_enabled=False), memory=memory)
        context=ToolContext(SimpleNamespace(is_ready=lambda:True),None,SimpleNamespace(id=3),SimpleNamespace(id=1))
        local=[]; errors=0
        for index in range(200):
            started=time.perf_counter()
            result=await engine.ask(AIRequest(index,None,3,'calculate (25 + 5) * 4'),context)
            local.append((time.perf_counter()-started)*1000)
            errors += not result.success
        tracemalloc.start()
        for index in range(1000):
            engine.conversations.append((index,None,3),'hello friend','hello there')
        _,peak=tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result={
            'python':platform.python_version(), 'platform':platform.system(),
            'routing':summary(route), 'memory_lookup':summary(lookups),
            'retrieval_100_documents':summary(retrieval), 'deterministic_end_to_end':summary(local),
            'deterministic_external_calls':engine.providers.calls,
            'deterministic_error_rate':errors/200,
            'deterministic_cache_hit_rate':engine.local_skills.hits/200,
            'session_count':len(engine.conversations._sessions),
            'session_allocation_peak_bytes':peak,
            'process_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'model_first_token_ms':None,
            'model_end_to_end_ms':None,
            'notes':'Offline synthetic benchmark; 100 curated documents, no model loaded; first-token and model latency unmeasured.'
        }
        await rag.close()
        await engine.close()
        print(json.dumps(result,indent=2))

if __name__=='__main__':
    asyncio.run(main())
