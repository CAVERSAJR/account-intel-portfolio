import { describe, expect, it } from 'vitest';
import rawDataset from './data.json';
import type { Dataset } from './types';
import { createEngine } from './engine-core';

const dataset = rawDataset as Dataset;

describe('engine helpers used by the catch-up briefs and time-back estimate', () => {
  it('counts research volume, with only public sources in the source count', () => {
    const engine = createEngine(dataset);
    const stats = engine.stats();
    expect(stats.accounts).toBe(11);
    expect(stats.contacts).toBe(dataset.contacts.length);
    expect(stats.sources).toBe(dataset.sources.filter(source => source.kind === 'public').length);
    expect(stats.sources).toBeLessThan(dataset.sources.length);
  });

  it('scores an account without its dated event, without changing workspace state', () => {
    const engine = createEngine(dataset);
    const event = engine.eventSource('advent');
    expect(event).not.toBeNull();
    const before = engine.score('advent')!.total;
    const without = engine.scoreWithout('advent', event!.id)!.total;
    expect(before).toBeCloseTo(9.1, 1);
    expect(without).toBeCloseTo(4.0, 1);
    expect(engine.score('advent')!.total).toBe(before);
    expect(engine.eventSource('advent')!.active).toBe(true);
  });

  it('counts researched contacts per account', () => {
    const engine = createEngine(dataset);
    expect(engine.contactCount('francisco')).toBe(10);
    expect(engine.contactCount('summit')).toBe(6);
  });

  it('lists Battery Ventures contacts with the buying roles first and the date each role was checked', () => {
    const engine = createEngine(dataset);
    const people = engine.contacts('battery');
    expect(people).toHaveLength(8);
    expect(people.slice(0, 3).map(person => [person.name, person.role])).toEqual([
      ['Lizette Perez-Deisboeck', 'champion'], ['Chris Schiavo', 'budget'], ['Karen Bommart', 'ir']]);
    expect(people.every(person => person.checked === '2026-11-16')).toBe(true);
    expect(engine.score('battery')!.total).toBe(7.1);
  });

  it('puts the seller-chosen recipient in the request only when that contact profile is an active source', () => {
    const engine = createEngine(dataset);
    const champion = engine.contacts('battery')[0];
    const chosen = engine.request('battery', 'LP obligation tracking', champion.id);
    expect(chosen.recipient).toBe(champion.id);
    expect(chosen.body.context).toMatchObject({ recipient: `${champion.id}-profile` });
    expect(chosen.body.evidence.some(item => item.id === `${champion.id}-profile`)).toBe(true);
    const none = engine.request('battery', 'LP obligation tracking');
    expect(none.recipient).toBeNull();
    expect('recipient' in none.body.context).toBe(false);
    // A contact from another account is ignored, not sent.
    const other = engine.request('battery', 'LP obligation tracking', engine.contacts('advent')[0].id);
    expect(other.recipient).toBeNull();
  });
});
