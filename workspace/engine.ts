// Browser bundle entry. Local build with the full research sample.
import rawDataset from './data.json';
import type { Dataset } from './types';
import { createEngine } from './engine-core';

(window as unknown as { AccountIntelEngine: ReturnType<typeof createEngine> }).AccountIntelEngine = createEngine(rawDataset as Dataset);
