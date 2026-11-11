export function Select({ value, onChange, options, placeholder, className = "" }: {
  value: string; onChange: (v: string) => void; options: Record<string, string>; placeholder?: string; className?: string;
}) {
  return (
    <select className={`h-9 rounded-md border bg-background px-2 text-sm ${className}`} value={value} onChange={(e) => onChange(e.target.value)}>
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {Object.entries(options).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
    </select>
  );
}
