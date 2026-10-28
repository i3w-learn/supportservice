import { MapPin } from "lucide-react"

import { useCentre } from "@/lib/firestore"
import type { Centre, CentreRef } from "@/lib/types"

// Fields with their own place in the layout. Everything else the sheet
// carries (hardware serials, software versions, warranty dates) is listed
// generically below them, so a new column needs no dashboard change.
const NAMED = new Set([
  "centreId",
  "block",
  "blockEn",
  "village",
  "villageEn",
  "serial",
  "govtCode",
  "workerName",
  "workerPhone",
  "fieldPerson",
  "updatedAt",
])

/** "smartBoardSerial" → "Smart board serial". */
function humanise(key: string): string {
  const spaced = key.replace(/([a-z0-9])([A-Z])/g, "$1 $2").replace(/_/g, " ")
  return spaced.charAt(0).toUpperCase() + spaced.slice(1).toLowerCase()
}

function extras(centre: Centre): [string, string][] {
  return Object.entries(centre)
    .filter(([key, value]) => !NAMED.has(key) && value !== "" && value != null)
    .map(([key, value]) => [humanise(key), String(value)] as [string, string])
    .sort(([a], [b]) => a.localeCompare(b))
}

export function CentrePanel({ centre: ref }: { centre: CentreRef | null | undefined }) {
  const centre = useCentre(ref?.centreId)

  if (!ref) {
    return (
      <div className="flex flex-col gap-1.5 text-sm text-muted-foreground">
        <p className="font-medium text-foreground">No centre linked.</p>
        <p>
          The contact did not scan a centre QR code and their number is not in the centre sheet.
          Add their number as the worker phone for their centre and the next ticket will be placed
          automatically.
        </p>
      </div>
    )
  }

  const full = centre ?? ref
  const rows: [string, string | undefined][] = [
    ["Centre ID", full.centreId],
    ["Govt AWC code", centre?.govtCode],
    ["Worker", centre?.workerName],
    ["Worker phone", centre?.workerPhone && `+${centre.workerPhone}`],
    ["Field person", centre?.fieldPerson],
  ]

  return (
    <div className="flex flex-col gap-4 text-sm">
      <div className="flex items-start gap-2.5">
        <MapPin className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        <div>
          <p className="text-base font-semibold leading-tight">
            {full.village} <span className="font-normal text-muted-foreground">{full.villageEn}</span>
          </p>
          <p className="text-muted-foreground">
            {full.block} · {full.blockEn}
          </p>
        </div>
      </div>

      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1.5">
        {rows
          .filter((row): row is [string, string] => Boolean(row[1]))
          .map(([label, value]) => (
            <Row key={label} label={label} value={value} />
          ))}
      </dl>

      {centre && extras(centre).length > 0 && (
        <>
          <p className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
            Inventory & details
          </p>
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1.5">
            {extras(centre).map(([label, value]) => (
              <Row key={label} label={label} value={value} />
            ))}
          </dl>
        </>
      )}

      {!centre && (
        <p className="text-xs text-muted-foreground">
          Centre record not found in the centre list — only what the ticket carries is shown.
        </p>
      )}
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </>
  )
}
