import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import {
  CHALLENGER_DEEP_M,
  estimatePressureAtm,
  estimateTemperatureC,
  explorerCreatures,
  explorerLandmarks,
  formatExplorerDepth,
  getZoneAtDepth,
} from '~/lib/explorer'
import { oceanZones } from '~/lib/ocean-data'

type DepthStyle = CSSProperties & { '--marker-depth'?: string }

export function DepthExplorer() {
  const viewportRef = useRef<HTMLDivElement>(null)
  const frameRef = useRef<number | null>(null)
  const [depthM, setDepthM] = useState(0)
  const zone = useMemo(() => getZoneAtDepth(depthM), [depthM])
  const pressureAtm = estimatePressureAtm(depthM)
  const temperatureC = estimateTemperatureC(depthM)

  const updateFromScroll = useCallback(() => {
    if (frameRef.current !== null) return
    frameRef.current = window.requestAnimationFrame(() => {
      const viewport = viewportRef.current
      if (viewport) setDepthM(Math.min(CHALLENGER_DEEP_M, Math.max(0, viewport.scrollTop)))
      frameRef.current = null
    })
  }, [])

  useEffect(() => {
    const viewport = viewportRef.current
    if (!viewport) return
    viewport.addEventListener('scroll', updateFromScroll, { passive: true })
    return () => {
      viewport.removeEventListener('scroll', updateFromScroll)
      if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current)
    }
  }, [updateFromScroll])

  const moveToDepth = useCallback((nextDepthM: number) => {
    const clamped = Math.min(CHALLENGER_DEEP_M, Math.max(0, nextDepthM))
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    viewportRef.current?.scrollTo({ top: clamped, behavior: reducedMotion ? 'auto' : 'smooth' })
    setDepthM(clamped)
  }, [])

  return (
    <section className="explorer-shell" aria-labelledby="explorer-title">
      <div className="explorer-controls shell">
        <div>
          <p className="eyebrow">Interactive depth profile</p>
          <h2 id="explorer-title">Scroll 10,935 meters to Challenger Deep.</h2>
          <p>
            Depth placement is linear: one screen-scroll pixel represents approximately one meter. Pressure
            and temperature are illustrative estimates, not live sensor observations.
          </p>
        </div>
        <div className="explorer-jumps" aria-label="Jump to depth">
          {explorerLandmarks.map((landmark) => (
            <button key={landmark.depthM} type="button" onClick={() => moveToDepth(landmark.depthM)}>
              {landmark.depthM === 0 ? 'Surface' : `${landmark.depthM.toLocaleString()} m`}
            </button>
          ))}
        </div>
        <label className="depth-slider">
          <span>Depth control</span>
          <input
            type="range"
            min="0"
            max={CHALLENGER_DEEP_M}
            step="1"
            value={Math.round(depthM)}
            onChange={(event) => moveToDepth(Number(event.currentTarget.value))}
          />
        </label>
      </div>

      <div className="explorer-stage">
        <div className="explorer-hud" aria-live="polite">
          <div>
            <span>Depth</span>
            <strong>{formatExplorerDepth(depthM)}</strong>
          </div>
          <div>
            <span>Zone</span>
            <strong>{zone.name}</strong>
          </div>
          <div>
            <span>Pressure</span>
            <strong>≈ {Math.round(pressureAtm).toLocaleString()} atm</strong>
          </div>
          <div>
            <span>Temperature</span>
            <strong>≈ {temperatureC.toFixed(1)}°C</strong>
          </div>
          <div>
            <span>Light</span>
            <strong>{zone.light}</strong>
          </div>
        </div>

        <div
          className="explorer-viewport"
          ref={viewportRef}
          role="region"
          aria-label="Scrollable ocean-depth explorer"
          tabIndex={0}
        >
          <div className="explorer-track" style={{ height: `calc(${CHALLENGER_DEEP_M}px + 76vh)` }}>
            {oceanZones.map((item) => {
              const start = Math.min(item.minDepthM, CHALLENGER_DEEP_M)
              const end = Math.min(item.maxDepthM, CHALLENGER_DEEP_M)
              return (
                <div
                  key={item.slug}
                  className={`explorer-zone explorer-zone-${item.slug}`}
                  style={{ top: `calc(38vh + ${start}px)`, height: `${Math.max(0, end - start)}px` }}
                >
                  <a href={`/zones/${item.slug}`}>
                    <span>{item.scientificName}</span>
                    <strong>{item.name}</strong>
                  </a>
                </div>
              )
            })}

            {explorerLandmarks.map((landmark) => (
              <div
                className="explorer-landmark"
                key={landmark.depthM}
                style={{ top: `calc(38vh + ${landmark.depthM}px)` }}
              >
                <span>{landmark.depthM.toLocaleString()} m</span>
                <div>
                  <strong>{landmark.label}</strong>
                  <small>{landmark.detail}</small>
                </div>
              </div>
            ))}

            {explorerCreatures.map((creature) => (
              <a
                className={`explorer-creature explorer-creature-${creature.side}`}
                href={`/creatures/${creature.slug}`}
                key={creature.slug}
                style={{ '--marker-depth': `calc(38vh + ${creature.markerDepthM}px)` } as DepthStyle}
              >
                <span>{creature.markerDepthM.toLocaleString()} m</span>
                <strong>{creature.name}</strong>
                <small>{creature.summary}</small>
              </a>
            ))}
          </div>
        </div>
        <div className="explorer-read-line" aria-hidden="true"><span>Current depth</span></div>
      </div>
    </section>
  )
}
