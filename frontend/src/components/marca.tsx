import { useId } from "react";

/** Identidade visual "Agente de Marcas": monograma em escudo (proteção da marca) com o selo ®. */
export const NOME_SISTEMA = "Agente de Marcas";

export function LogoAgente({ className = "size-9" }: { className?: string }) {
  const id = `am-g${useId().replace(/:/g, "")}`;  // id único: várias cópias do logo na mesma página
  return (
    <svg viewBox="0 0 40 40" className={className} role="img" aria-label={NOME_SISTEMA}>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#38bdf8" />
          <stop offset="1" stopColor="#1d4ed8" />
        </linearGradient>
      </defs>
      <path d="M20 2.5 34.5 8v11.2c0 9-6.1 15.6-14.5 18.3C11.6 34.8 5.5 28.2 5.5 19.2V8z" fill={`url(#${id})`} />
      <path d="M20 2.5 34.5 8v11.2c0 9-6.1 15.6-14.5 18.3" fill="#0b1f3a" opacity=".18" />
      <path d="M13.2 27.5 20 11l6.8 16.5h-3.4l-1.3-3.4h-4.2l-1.3 3.4zm5-6.2h3.6L20 16.5z" fill="#fff" />
      <circle cx="29.5" cy="29.5" r="5.2" fill="#0b1f3a" stroke="#fff" strokeWidth="1.3" />
      <text x="29.5" y="32.3" textAnchor="middle" fontSize="7.5" fontWeight="700" fill="#fff" fontFamily="Arial, sans-serif">R</text>
    </svg>
  );
}
