# Package-lock status

A `package-lock.json` could not be generated in the artifact environment because both public npm access and the available internal mirror failed to resolve the pinned TanStack dependency set. The package versions in `package.json` were rechecked against current npm package pages and corrected before packaging.

The first successful local `npm install` must create `package-lock.json`; commit that lockfile before treating CI installs as deterministic. Until then, dependency installation and the full framework build are unproven.
