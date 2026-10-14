import { useEffect, useId, useRef, useState } from "react";
import { searchPlaces } from "../lib/api";
import type { Place, PlaceValue } from "../lib/types";

type Props = {
  label: string;
  value: PlaceValue;
  onChange: (value: PlaceValue) => void;
  placeholder?: string;
  marker: "origin" | "destination";
};

const textOf = (v: PlaceValue) => (typeof v === "string" ? v : v.label);

export default function PlaceInput({ label, value, onChange, placeholder, marker }: Props) {
  const id = useId();
  const [text, setText] = useState(textOf(value));
  const [results, setResults] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [loading, setLoading] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  // Keep the box in sync when the parent sets a value (e.g. sample trips, swap).
  useEffect(() => setText(textOf(value)), [value]);

  useEffect(() => {
    if (typeof value !== "string" || value.trim().length < 3) {
      setResults([]);
      return;
    }
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true);
      searchPlaces(value.trim(), ctrl.signal)
        .then((r) => {
          setResults(r);
          setActive(0);
        })
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 300);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [value]);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const choose = (p: Place) => {
    onChange(p);
    setText(p.label);
    setOpen(false);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!open || !results.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (a + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a - 1 + results.length) % results.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(results[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const resolved = typeof value !== "string";

  return (
    <div className="field place-field" ref={wrapRef}>
      <label htmlFor={id}>{label}</label>
      <div className={`place-input ${resolved ? "is-resolved" : ""}`}>
        <span className={`place-dot place-dot--${marker}`} aria-hidden />
        <input
          id={id}
          type="text"
          value={text}
          placeholder={placeholder}
          autoComplete="off"
          role="combobox"
          aria-expanded={open && results.length > 0}
          aria-controls={`${id}-list`}
          onChange={(e) => {
            setText(e.target.value);
            onChange(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
        />
        {loading && <span className="spinner spinner--small" aria-label="Searching" />}
        {resolved && !loading && <span className="place-check" title="Location confirmed">✓</span>}
      </div>
      {open && results.length > 0 && (
        <ul className="place-results" id={`${id}-list`} role="listbox">
          {results.map((p, i) => (
            <li
              key={`${p.lat},${p.lon},${i}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? "active" : ""}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(p);
              }}
              onMouseEnter={() => setActive(i)}
            >
              {p.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
