import { cellSpoken, cellText, scaleMax, type Row } from "@/lib/api/stats-adapter";

type Props = {
  /** Table caption: what the bars count. */
  caption: string;
  rows: Row[];
  /** Header of the label column. */
  labelHeader: string;
  /** Header of the count column. */
  countHeader?: string;
};

/**
 * A bar chart that is a real table: each row has its label, its count as text, and a
 * bar drawn to scale (aria-hidden; the count is the data). A suppressed cell ("<5") is
 * never drawn as a bar: it shows "hidden, under 5" in place of the bar, and it does
 * not set the scale.
 */
export function BarTable({ caption, rows, labelHeader, countHeader = "Videos" }: Props) {
  const max = scaleMax(rows);
  return (
    <table className="w-full table-fixed border-collapse text-small">
      <caption className="sr-only">{caption}. Counts under 5 are hidden and shown as &lt;5.</caption>
      <thead className="sr-only">
        <tr>
          <th scope="col">{labelHeader}</th>
          <th scope="col">{countHeader}</th>
          <th scope="col">Bar</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.key} data-row={r.key} className="border-b border-line last:border-0">
            <th scope="row" className="w-[42%] py-2 pr-3 text-left align-middle font-normal text-ink [overflow-wrap:anywhere]">
              {r.label}
              {r.hint && <span className="hidden text-cap text-ink-3 sm:block">{r.hint}</span>}
            </th>
            <td className="w-14 py-2 pr-3 text-right align-middle font-semibold tabular-nums text-ink" data-cell={r.cell.suppressed ? "suppressed" : r.cell.n}>
              <span aria-hidden="true">{cellText(r.cell)}</span>
              <span className="sr-only">{cellSpoken(r.cell)}</span>
            </td>
            <td aria-hidden="true" className="py-2 align-middle">
              {r.cell.suppressed ? (
                <span data-bar="suppressed" className="inline-flex items-center rounded-sm border border-dashed border-line-input px-1.5 text-cap italic text-ink-3">
                  hidden, under 5
                </span>
              ) : (
                <span className="block h-3 rounded-sm bg-surface-sunken">
                  <span data-bar={r.cell.n} className="block h-3 rounded-sm bg-primary" style={{ width: `${max ? Math.max(2, (r.cell.n / max) * 100) : 0}%` }} />
                </span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
