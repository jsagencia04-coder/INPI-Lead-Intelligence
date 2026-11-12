export function Select({ value, onChange, options, placeholder, className = "" }: {
  value: string; onChange: (v: string) => void; options: Record<string, string>; placeholder?: string; className?: string;
}) {
  return (
    <select className={`h-9 rounded-lg border bg-card px-2 text-sm shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 ${className}`} value={value} onChange={(e) => onChange(e.target.value)}>
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {Object.entries(options).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
    </select>
  );
}
