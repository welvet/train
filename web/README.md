# Train web UI

A responsive Next.js and TypeScript UI for monitoring and controlling the train
system through the backend's public web API.

## Requirements

- Node.js 20.9 or newer
- npm

## Development

```sh
npm install
npm run dev
```

The development server is only for local iteration.

## Static build

```sh
npm ci
npm run build
```

Next.js writes the static site to `out/`. The release builder packages that
directory into the Python wheel, and the backend web API serves it from `/`.
A Node.js server is not required in production.

## Checks

```sh
npm run lint
npm run typecheck
npm test
```

The frontend API types are generated from the backend-owned OpenAPI contract:

```sh
tools/generate-web-contract
cd web
npm run generate:api
```

Generated files under `src/api/generated/` must not be edited manually.
