# ELECTRIA Web

Frontend para ELECTRIA - Inteligencia Artificial para el Mercado Eléctrico.

## Stack Tecnológico

- **Framework**: Next.js 14 (App Router)
- **Styling**: Tailwind CSS
- **State**: Zustand + React Query
- **UI Components**: shadcn/ui (custom)
- **Charts**: Recharts
- **Animations**: Framer Motion

## Estructura del Proyecto

```
electria-web/
├── src/
│   ├── app/              # Next.js App Router
│   │   ├── (marketing)/  # Landing, pricing, etc.
│   │   ├── (auth)/       # Login, signup
│   │   ├── (dashboard)/  # App principal
│   │   └── api/          # API routes (si necesario)
│   ├── components/
│   │   ├── ui/           # Componentes base (botones, inputs)
│   │   ├── chat/         # Componentes del chat
│   │   ├── dashboard/    # Widgets y gráficos
│   │   ├── marketing/    # Landing page components
│   │   └── shared/       # Componentes compartidos
│   ├── lib/
│   │   ├── hooks/        # Custom hooks
│   │   ├── stores/       # Zustand stores
│   │   ├── utils/        # Utilidades
│   │   └── api/          # API client
│   └── types/            # TypeScript types
├── public/
│   ├── images/
│   └── icons/
└── tests/
```

## Setup Local

### Requisitos

- Node.js 20+
- pnpm

### Instalación

```bash
# Clonar repositorio
git clone https://github.com/[tu-usuario]/electria-web.git
cd electria-web

# Instalar dependencias
pnpm install

# Copiar variables de entorno
cp .env.example .env.local
# Editar .env.local con tus credenciales

# Ejecutar servidor de desarrollo
pnpm dev
```

La aplicación estará disponible en http://localhost:3000

## Desarrollo

```bash
# Desarrollo
pnpm dev

# Build producción
pnpm build

# Ejecutar build
pnpm start

# Linting
pnpm lint
pnpm lint:fix

# Formateo
pnpm format

# Type checking
pnpm typecheck

# Tests
pnpm test
```

## Guía de Diseño

Ver `CLAUDE.md` en la raíz del proyecto para:
- Paleta de colores
- Tipografía
- Componentes
- Animaciones

### Colores Principales

```css
--brand-500: #0ea5e9;  /* Azul eléctrico */
--accent-500: #06b6d4; /* Cyan */
--success: #10b981;    /* Verde */
```

## Licencia

Propietario - ELECTRIA
