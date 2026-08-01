import { describe, it, expect } from 'vitest';

import {
  AMOUNTS_NOTE,
  amountsUnpopulated,
  edgeTone,
  entityTone,
  fmtMoney,
  statusRole,
} from '@/lib/cs-format';

// cs-format.js is small, but fmtMoney renders award amounts on a public-money
// oversight surface, and amountsUnpopulated decides whether the Tranche A
// caveat appears at all. Both fail quietly: a wrong amount still looks like an
// amount, and a suppressed caveat still looks like a complete dataset.

describe('fmtMoney', () => {
  it('formats a whole-dollar amount with no cents', () => {
    expect(fmtMoney(1234567)).toBe('$1,234,567');
  });

  it('renders an em dash for a missing amount', () => {
    // U+2014, not a hyphen — assert the exact character.
    expect(fmtMoney(null)).toBe('—');
    expect(fmtMoney(undefined)).toBe('—');
  });

  it('renders a genuine zero as $0, not as missing', () => {
    // The guard is `v == null`, deliberately not `!v`. A zero-dollar award is a
    // fact about a contract; showing it as an em dash would report it as data we
    // do not have.
    expect(fmtMoney(0)).toBe('$0');
  });

  it('rounds rather than truncating', () => {
    // maximumFractionDigits: 0. Truncation would understate every rounded-up
    // amount by a dollar, consistently and invisibly.
    expect(fmtMoney(1234.5)).toBe('$1,235');
    expect(fmtMoney(1234.4)).toBe('$1,234');
  });

  it('formats a negative amount rather than dropping the sign', () => {
    expect(fmtMoney(-500)).toBe('-$500');
  });

  it('renders an empty string as $0 — a known sharp edge', () => {
    // `'' == null` is false, so an empty CSV cell that arrives as '' rather than
    // null coerces to 0 inside Intl and renders as a real zero-dollar award.
    // Pinned deliberately: if the loader's null handling ever changes, this test
    // is where that shows up, rather than in a report someone reads as fact.
    expect(fmtMoney('')).toBe('$0');
  });
});

describe('amountsUnpopulated', () => {
  // Gates the Tranche A caveat in both StatsBar and MunicipalityAggregates, so
  // the two surfaces cannot disagree about whether amounts are trustworthy.

  it('is true when no contract carries an amount', () => {
    expect(amountsUnpopulated({ contractsWithAmount: 0 })).toBe(true);
  });

  it('is false as soon as one contract does', () => {
    expect(amountsUnpopulated({ contractsWithAmount: 1 })).toBe(false);
  });

  it('treats absent stats as unpopulated rather than assuming the best', () => {
    // `?? 0` — if stats have not loaded, or the field is missing, the caveat
    // shows. Failing the other way would present an incomplete dataset as
    // complete, which is the more damaging error on a spending surface.
    expect(amountsUnpopulated(undefined)).toBe(true);
    expect(amountsUnpopulated(null)).toBe(true);
    expect(amountsUnpopulated({})).toBe(true);
  });

  it('has a caveat string to show', () => {
    expect(AMOUNTS_NOTE).toBeTruthy();
  });
});

describe('tone lookups', () => {
  it.each([
    ['agency'],
    ['utility'],
    ['firm'],
    ['fund'],
    ['person'],
  ])('gives the %s entity type a tone of its own', (type) => {
    expect(entityTone(type)).not.toBe(entityTone('not-an-entity-type'));
  });

  it('keeps every entity tone distinct', () => {
    const tones = ['agency', 'utility', 'firm', 'fund', 'person'].map(entityTone);

    expect(new Set(tones).size).toBe(5);
  });

  it.each([
    ['active', 'success'],
    ['flagged', 'danger'],
    ['amended', 'warning'],
    ['executed', 'info'],
  ])('maps contract status %s to the federation role %s', (status, role) => {
    expect(statusRole(status)).toBe(role);
  });

  it('does not let flagged and active collapse into the same role', () => {
    // The one pairing that matters: `flagged` is the reason this surface exists.
    expect(statusRole('flagged')).not.toBe(statusRole('active'));
    expect(statusRole('flagged')).not.toBe(statusRole('unknown-status'));
  });

  it('falls back to neutral and slate for values it does not know', () => {
    expect(statusRole('not-a-status')).toBe('neutral');
    expect(statusRole(undefined)).toBe('neutral');
    expect(entityTone(undefined)).toContain('slate');
    expect(edgeTone(undefined)).toBe('text-slate-300');
  });

  it('keeps every edge type distinct', () => {
    const types = ['LOCATED_IN', 'AWARDED_TO', 'CONTROLS', 'AFFILIATED_WITH', 'SUBSIDIARY_OF'];

    expect(new Set(types.map(edgeTone)).size).toBe(types.length);
  });
});
