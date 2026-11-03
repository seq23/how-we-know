
import Foundation
import Vision
import AppKit
// One line per image: path TAB json([{t: text, x, y, w, h}]) in normalised
// image coordinates with the ORIGIN AT TOP-LEFT (Vision reports bottom-left,
// so y is flipped here). Boxes matter as much as the text: a NOAA wordmark bug
// pinned in a corner is croppable, a chyron across the middle is not.
for path in CommandLine.arguments.dropFirst() {
  guard let img = NSImage(contentsOfFile: path),
        let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    print("\(path)\tERR"); continue }
  let req = VNRecognizeTextRequest()
  req.recognitionLevel = .accurate
  req.usesLanguageCorrection = false
  try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
  var items: [[String: Any]] = []
  for o in (req.results ?? []) {
    guard let c = o.topCandidates(1).first else { continue }
    let b = o.boundingBox
    items.append(["t": c.string, "x": b.minX, "y": 1.0 - b.maxY,
                  "w": b.width, "h": b.height])
  }
  let data = try! JSONSerialization.data(withJSONObject: items, options: [])
  print("\(path)\t\(String(data: data, encoding: .utf8)!)")
}
