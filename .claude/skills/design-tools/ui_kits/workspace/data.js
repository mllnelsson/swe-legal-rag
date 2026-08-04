const RESULTS = [
  {
    id: "novak", title: "Novak v. Harrow Logistics, Inc.", citation: "812 F.3d 1044", court: "9th Cir.", year: "2016",
    authority: "binding", treatment: "Followed",
    excerpt: "A carrier that accepts goods for delivery assumes a duty of reasonable care toward every party it knows will take possession downstream, not merely the consignee named on the bill of lading.",
    matchTerms: ["duty of care", "consignee", "bill of lading"],
  },
  {
    id: "carmack", title: "49 U.S.C. § 14706 — Liability of carriers under receipts and bills of lading", citation: "49 U.S.C. § 14706", court: "Statute", year: "",
    authority: "binding",
    excerpt: "A carrier is liable to the person entitled to recover under the receipt or bill of lading for the actual loss or injury to the property caused by it or by any other carrier over whose line the property is transported.",
    matchTerms: ["actual loss", "bill of lading"],
  },
  {
    id: "ellery", title: "Ellery Freight Sys. v. Marchand Produce Co.", citation: "704 F. App'x 512", court: "6th Cir.", year: "2017",
    authority: "persuasive", treatment: "Criticized",
    excerpt: "Foreseeability alone does not create a duty where the parties' allocation of risk is fixed by the tariff; the consignee's remedy lies in contract.",
    matchTerms: ["foreseeability", "tariff"],
  },
  {
    id: "restatement", title: "Restatement (Second) of Torts § 324A", citation: "Restatement (2d) Torts § 324A", court: "Secondary", year: "1965",
    authority: "secondary",
    excerpt: "One who undertakes to render services to another which he should recognize as necessary for the protection of a third person is subject to liability to the third person for physical harm resulting from failure to exercise reasonable care.",
    matchTerms: ["third person", "reasonable care"],
  },
  {
    id: "delgado", title: "Delgado Bros. Trucking v. Pacific Cold Storage", citation: "2019 WL 3821194", court: "N.D. Cal.", year: "2019",
    authority: "persuasive",
    excerpt: "Applying Novak, the court held that a cold-storage consignee not named on the bill of lading could nonetheless recover where the carrier's dispatch records showed the delivery chain.",
    matchTerms: ["consignee", "delivery chain"],
  },
];

const MATTERS = [
  { value: "novak", label: "Novak v. Harrow", icon: "folder", count: 12 },
  { value: "delaney", label: "Delaney acquisition", icon: "folder", count: 4 },
  { value: "kessler", label: "Kessler arbitration", icon: "folder", count: 7 },
];

const SUGGESTED = [
  "Does a motor carrier owe a duty of care to a downstream consignee?",
  "Ninth Circuit standard for Carmack Amendment preemption",
  "When is an unpublished disposition citable in the 9th Circuit?",
];

const HISTORY = [
  { q: "Carmack preemption of state negligence claims", when: "Today, 09:14", n: 31 },
  { q: "Duty of care to downstream consignee", when: "Yesterday", n: 48 },
  { q: "Tariff allocation of risk — 6th Cir.", when: "Mon", n: 12 },
];

const ANSWER = "Within the Ninth Circuit, a carrier's duty of reasonable care runs to the consignee named on the bill of lading, and Novak extends it to a downstream consignee whose possession was reasonably foreseeable. District courts have applied that reading where dispatch records establish the delivery chain. The Sixth Circuit takes the narrower view that a tariff's allocation of risk forecloses a tort duty, so the analysis turns on where the claim is filed. Claims for loss or damage in transit remain preempted by the Carmack Amendment regardless of circuit.";

Object.assign(window, { RESULTS, MATTERS, SUGGESTED, HISTORY, ANSWER });
