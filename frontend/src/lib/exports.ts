// exports.ts -- client-side Excel (SheetJS) and PDF (jsPDF + autotable)
// export of an operation bulletin + costing summary, in the layout IE teams
// already circulate: operation / machine / SMV / running total, with a
// costing footer. Every number written here is read off a BulletinOut /
// CostingReport already fetched from the API -- nothing is computed here.
import * as XLSX from "xlsx";
import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";
import type { BulletinOut, CostingReport, StyleOut } from "../api/types";

interface BulletinRow {
  seq: number;
  name: string;
  machineClass: string;
  stOpMin: number;
  runningTotalMin: number;
}

function machineClassesFor(auditTrail: unknown): string {
  const trail = auditTrail as { steps?: Array<Record<string, unknown>> } | undefined;
  const steps = trail?.steps;
  if (!Array.isArray(steps)) return "—";
  const classes = new Set<string>();
  for (const s of steps) {
    const mc = s["machine_class"];
    if (typeof mc === "string" && mc) classes.add(mc);
  }
  return classes.size ? Array.from(classes).join(", ") : "manual/handling";
}

function buildRows(bulletin: BulletinOut): BulletinRow[] {
  let running = 0;
  return bulletin.operations.map((op) => {
    const stMin = op.latest_result?.st_op_min ?? 0;
    running += stMin;
    return {
      seq: op.sequence + 1,
      name: op.name,
      machineClass: machineClassesFor(op.latest_result?.audit_trail),
      stOpMin: stMin,
      runningTotalMin: running,
    };
  });
}

export function exportBulletinToExcel(
  bulletin: BulletinOut,
  costing: CostingReport | null,
  filename = "operation_bulletin.xlsx"
) {
  const rows = buildRows(bulletin);
  const sheetData: (string | number)[][] = [
    ["Style", bulletin.style.name],
    ["Garment type", bulletin.style.garment_type],
    ["Variant", bulletin.style.variant],
    ["Size", bulletin.style.size],
    [],
    ["#", "Operation", "Machine", "SMV (min)", "Running total (min)"],
    ...rows.map((r) => [r.seq, r.name, r.machineClass, Number(r.stOpMin.toFixed(4)), Number(r.runningTotalMin.toFixed(4))]),
    [],
    ["Style SMV (min)", bulletin.smv_min ?? 0],
    ["Style SMV (TMU)", bulletin.smv_tmu ?? 0],
  ];
  if (costing) {
    sheetData.push(
      [],
      ["Costing summary"],
      ["Labour rate / hour", costing.labour_rate_per_hour],
      ["Efficiency", costing.efficiency],
      ["Cost per garment", Number(costing.cost_per_garment.toFixed(4))]
    );
  }
  const ws = XLSX.utils.aoa_to_sheet(sheetData);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "Operation Bulletin");
  XLSX.writeFile(wb, filename);
}

export function exportBulletinToPdf(
  bulletin: BulletinOut,
  costing: CostingReport | null,
  filename = "operation_bulletin.pdf"
) {
  const rows = buildRows(bulletin);
  const doc = new jsPDF();
  const style: StyleOut = bulletin.style;

  doc.setFontSize(14);
  doc.text("Operation Bulletin", 14, 16);
  doc.setFontSize(10);
  doc.text(`${style.name}  |  ${style.garment_type} / ${style.variant} / ${style.size}`, 14, 23);

  autoTable(doc, {
    startY: 28,
    head: [["#", "Operation", "Machine", "SMV (min)", "Running total (min)"]],
    body: rows.map((r) => [
      r.seq,
      r.name,
      r.machineClass,
      r.stOpMin.toFixed(4),
      r.runningTotalMin.toFixed(4),
    ]),
    styles: { fontSize: 8 },
    headStyles: { fillColor: [40, 40, 60] },
  });

  const afterTableY = (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY + 8;
  doc.setFontSize(11);
  doc.text(
    `Style SMV: ${(bulletin.smv_min ?? 0).toFixed(4)} min  (${(bulletin.smv_tmu ?? 0).toFixed(1)} TMU)`,
    14,
    afterTableY
  );

  let y = afterTableY + 8;
  if (costing) {
    doc.setFontSize(12);
    doc.text("Costing summary", 14, y);
    y += 6;
    doc.setFontSize(10);
    doc.text(`Labour rate / hour: ${costing.labour_rate_per_hour}`, 14, y);
    y += 5;
    doc.text(`Efficiency: ${(costing.efficiency * 100).toFixed(1)}%`, 14, y);
    y += 5;
    doc.text(`Cost per garment: ${costing.cost_per_garment.toFixed(4)}`, 14, y);
  }

  doc.save(filename);
}
