import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import { useSortable } from '@/lib/use-sortable';

// useSortable backs every sortable table in the dashboard. It is a real hook
// (useState + useMemo), so it is exercised through renderHook rather than
// called directly. Most of what is worth pinning here is not the happy path —
// it is the comparator's three deliberate asymmetries, each of which produces a
// plausible-looking wrong order rather than an error.

const rows = [
  { name: 'Ponce', amount: 300 },
  { name: 'arecibo', amount: 100 },
  { name: 'Bayamón', amount: 200 },
];

const names = (result) => result.current.sorted.map((r) => r.name);

describe('useSortable — unsorted', () => {
  it('returns the rows untouched, and by identity, before any sort', () => {
    // Not a copy: callers rely on the reference being stable so an unsorted
    // table does not re-render on every parent render.
    const { result } = renderHook(() => useSortable(rows));

    expect(result.current.sorted).toBe(rows);
    expect(result.current.key).toBeNull();
  });

  it('honours an initial key and direction', () => {
    const { result } = renderHook(() => useSortable(rows, 'amount', 'desc'));

    expect(names(result)).toEqual(['Ponce', 'Bayamón', 'arecibo']);
  });
});

describe('useSortable — comparator', () => {
  it('compares numbers numerically, not as strings', () => {
    // The string branch would order 100, 200, 300 correctly by accident; use
    // values where the two orderings differ.
    const { result } = renderHook(() =>
      useSortable([{ n: 9 }, { n: 10 }, { n: 100 }], 'n'),
    );

    expect(result.current.sorted.map((r) => r.n)).toEqual([9, 10, 100]);
  });

  it('falls back to string comparison unless BOTH values are numbers', () => {
    // `typeof av === 'number' && typeof bv === 'number'` — a column that mixes a
    // number and a numeric string compares as text, so 10 sorts before 9.
    const { result } = renderHook(() =>
      useSortable([{ n: 9 }, { n: '10' }], 'n'),
    );

    expect(result.current.sorted.map((r) => r.n)).toEqual(['10', 9]);
  });

  it('compares strings case-insensitively', () => {
    // A naive `<` would put every capitalised name before every lowercase one.
    const { result } = renderHook(() => useSortable(rows, 'name'));

    expect(names(result)).toEqual(['arecibo', 'Bayamón', 'Ponce']);
  });

  it('orders accented municipio names by locale, not by code point', () => {
    // The corpus is Puerto Rico municipalities. localeCompare puts Añasco before
    // Arecibo; a code-point comparison would put it after Yauco, since "ñ" is
    // U+00F1.
    const { result } = renderHook(() =>
      useSortable([{ name: 'Yauco' }, { name: 'Añasco' }, { name: 'Arecibo' }], 'name'),
    );

    expect(names(result)).toEqual(['Añasco', 'Arecibo', 'Yauco']);
  });

  it('never mutates the input array', () => {
    const input = [{ n: 3 }, { n: 1 }, { n: 2 }];
    renderHook(() => useSortable(input, 'n'));

    expect(input.map((r) => r.n)).toEqual([3, 1, 2]);
  });
});

describe('useSortable — nullish handling', () => {
  // The documented rule, and the one most likely to be "fixed" into a bug: the
  // null checks return 1/-1 *before* `mul` is applied, so missing values sink to
  // the bottom in both directions. Award amounts are frequently null in Tranche
  // A, so this is the common case here, not an edge one.

  const withGaps = [{ v: 2 }, { v: null }, { v: 1 }, { v: undefined }];

  it('sinks nullish values to the bottom when ascending', () => {
    const { result } = renderHook(() => useSortable(withGaps, 'v'));

    expect(result.current.sorted.map((r) => r.v)).toEqual([1, 2, null, undefined]);
  });

  it('still sinks them to the bottom when descending', () => {
    // Direction-aware nulls would float them to the top here. That would look
    // correct — and would bury the rows an analyst actually wants to see.
    const { result } = renderHook(() => useSortable(withGaps, 'v', 'desc'));

    expect(result.current.sorted.slice(0, 2).map((r) => r.v)).toEqual([2, 1]);
    expect(result.current.sorted.slice(2).every((r) => r.v == null)).toBe(true);
  });

  it('treats two nullish values as equal rather than throwing', () => {
    const { result } = renderHook(() => useSortable([{ v: null }, { v: undefined }], 'v'));

    expect(result.current.sorted).toHaveLength(2);
  });

  it('does not treat 0 or an empty string as missing', () => {
    // `== null` is deliberate: a genuine zero-dollar award is data, and must sort
    // among the numbers rather than with the blanks.
    const { result } = renderHook(() =>
      useSortable([{ v: 5 }, { v: null }, { v: 0 }], 'v'),
    );

    expect(result.current.sorted.map((r) => r.v)).toEqual([0, 5, null]);
  });
});

describe('useSortable — the sort() toggler', () => {
  it('toggles direction when the same key is clicked again', () => {
    const { result } = renderHook(() => useSortable(rows, 'name'));

    expect(result.current.dir).toBe('asc');
    act(() => result.current.sort('name'));
    expect(result.current.dir).toBe('desc');
    act(() => result.current.sort('name'));
    expect(result.current.dir).toBe('asc');
  });

  it('resets to ascending when a different key is clicked', () => {
    // Carrying the previous direction over would silently show a new column
    // descending, which reads as the largest values being the default view.
    const { result } = renderHook(() => useSortable(rows, 'name'));

    act(() => result.current.sort('name')); // now desc
    act(() => result.current.sort('amount')); // different key

    expect(result.current.key).toBe('amount');
    expect(result.current.dir).toBe('asc');
  });

  it('sorts by a key that was not the initial one', () => {
    const { result } = renderHook(() => useSortable(rows));

    act(() => result.current.sort('amount'));

    expect(names(result)).toEqual(['arecibo', 'Bayamón', 'Ponce']);
  });
});
