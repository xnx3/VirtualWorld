import tempfile
import unittest
from pathlib import Path

from genesis.chain.block import Block
from genesis.chain.storage import ChainStorage


class ChainStorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_initialize_and_round_trip_block_and_world_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = ChainStorage(str(Path(tmpdir) / "chain.db"))
            await storage.initialize()

            genesis = Block.genesis_block("creator-node")
            await storage.save_block(genesis)
            await storage.save_world_state("phase", "EARLY_SILICON", 0)

            self.assertEqual(await storage.get_chain_height(), 0)
            loaded = await storage.get_latest_block()
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.hash, genesis.hash)
            self.assertEqual(await storage.get_world_state("phase"), "EARLY_SILICON")

            await storage.close()


if __name__ == "__main__":
    unittest.main()
