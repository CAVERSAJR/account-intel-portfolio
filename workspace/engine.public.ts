// Browser bundle entry. Hosted build: contact emails and LinkedIn links removed.
import rawDataset from './data.public.json';
import type { Dataset } from './types';
import { createEngine } from './engine-core';

(window as unknown as { AccountIntelEngine: ReturnType<typeof createEngine> }).AccountIntelEngine = createEngine(rawDataset as Dataset);
