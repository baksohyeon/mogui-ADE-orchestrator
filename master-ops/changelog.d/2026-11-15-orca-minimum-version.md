The template records a measured minimum Orca app version in the surface baseline, watches the worker and cleanup commands it calls, and reports below-minimum installations during preflight and surface checks.
Existing template installations need a restamp to receive the new minimum-version gate.
Missing or unparsable versions are reported as UNKNOWN so onboarding can distinguish an unavailable version from a parseable version below the minimum.
