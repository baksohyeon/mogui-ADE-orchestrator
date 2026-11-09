# Blame records

A blame record is one structured incident observation, written by the `blame-agent` skill as `BLAME-YYYY-MM-DD-<slug>.md`: what was observed, what was not, and where a causal claim outran the evidence. The template ships none. An install's own records are instance-owned, written into this directory by the seat that observed the incident, and never claimed by `MANIFEST.json`: the manifest lists `docs/blame/` under `instance_owned`, so this README stays on the template side and `template-apply` never writes or overwrites anything here.
