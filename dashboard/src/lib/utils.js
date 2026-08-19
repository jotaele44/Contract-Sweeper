import { clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs) {
  return twMerge(clsx(inputs))
}

// Look a key up in a plain object literal without inheriting from Object.prototype.
//
// `MAP[key] ?? fallback` looks like it degrades safely, and does for ordinary
// misses — but not for `__proto__`, `constructor`, `toString`, `valueOf` or
// `hasOwnProperty`. Those resolve through the prototype chain to a truthy object
// or function, so `??` never fires and the caller gets something that is not a
// value from the map at all.
//
// Here the keys are server-supplied (contract status, entity type, edge type) and
// the damage is contained: statusRole would hand federationTone an object that
// renders as "[object Object]", and a badge class would silently vanish, because
// clsx finds no own enumerable keys on the prototype and emits nothing — so the
// element loses its styling rather than degrading to slate. Not reachable from
// the frozen canonical_v1 vocabularies today.
//
// It is worth fixing anyway because the same pattern was a real crash in
// aguayluz-pr, where the key came from the URL: /sector/__proto__ passed an
// `if (!meta)` guard and threw on the next line.
export function lookup(map, key, fallback) {
  return Object.hasOwn(map, key) ? map[key] : fallback
}
