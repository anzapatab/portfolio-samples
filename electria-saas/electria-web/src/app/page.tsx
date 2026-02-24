import Link from "next/link";
import { ArrowRight, Zap, Search, Bell, BarChart3 } from "lucide-react";

export default function HomePage() {
  return (
    <main className="min-h-screen">
      {/* Hero Section */}
      <section className="relative overflow-hidden bg-gradient-hero">
        {/* Navigation */}
        <nav className="fixed top-0 z-50 w-full border-b border-border/40 bg-white/80 backdrop-blur-lg">
          <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
            <div className="flex items-center gap-2">
              <Zap className="h-8 w-8 text-brand-500" />
              <span className="text-xl font-bold">ELECTRIA</span>
            </div>
            <div className="hidden items-center gap-8 md:flex">
              <Link
                href="#features"
                className="text-sm text-muted-foreground hover:text-foreground"
              >
                Características
              </Link>
              <Link
                href="#pricing"
                className="text-sm text-muted-foreground hover:text-foreground"
              >
                Precios
              </Link>
              <Link
                href="/login"
                className="text-sm text-muted-foreground hover:text-foreground"
              >
                Iniciar sesión
              </Link>
              <Link
                href="/signup"
                className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-600"
              >
                Prueba gratis
              </Link>
            </div>
          </div>
        </nav>

        {/* Hero Content */}
        <div className="mx-auto max-w-7xl px-4 pb-24 pt-32 sm:px-6 lg:px-8 lg:pt-40">
          <div className="text-center">
            {/* Badge */}
            <div className="mb-6 inline-flex items-center rounded-full border border-brand-200 bg-brand-50 px-4 py-1.5">
              <span className="text-sm font-medium text-brand-700">
                Nuevo: Inteligencia competitiva para licitaciones
              </span>
            </div>

            {/* Headline */}
            <h1 className="mx-auto max-w-4xl text-4xl font-bold tracking-tight sm:text-5xl lg:text-6xl">
              Toda la inteligencia del{" "}
              <span className="text-gradient">mercado eléctrico</span> en un
              solo lugar
            </h1>

            {/* Subheadline */}
            <p className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground sm:text-xl">
              Consulta normativas, analiza costos marginales y recibe alertas
              del sector eléctrico chileno. Potenciado por IA, a una fracción
              del costo de las consultoras.
            </p>

            {/* CTAs */}
            <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
              <Link
                href="/signup"
                className="group flex items-center gap-2 rounded-lg bg-brand-500 px-6 py-3 font-medium text-white transition-all hover:bg-brand-600 hover:shadow-glow"
              >
                Comenzar prueba gratis
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
              </Link>
              <Link
                href="#demo"
                className="flex items-center gap-2 rounded-lg border border-border bg-white px-6 py-3 font-medium transition-colors hover:bg-muted"
              >
                Ver demostración
              </Link>
            </div>

            {/* Social Proof */}
            <p className="mt-8 text-sm text-muted-foreground">
              14 días gratis · Sin tarjeta de crédito · Cancela cuando quieras
            </p>
          </div>

          {/* Hero Image/Screenshot Placeholder */}
          <div className="mt-16">
            <div className="relative mx-auto max-w-5xl overflow-hidden rounded-xl border border-border bg-white shadow-2xl">
              <div className="aspect-[16/9] bg-gradient-to-br from-muted to-muted/50">
                <div className="flex h-full items-center justify-center">
                  <p className="text-muted-foreground">
                    [Screenshot del producto]
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="bg-white py-24">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
              Todo lo que necesitas para el mercado eléctrico
            </h2>
            <p className="mt-4 text-lg text-muted-foreground">
              Herramientas potentes, diseñadas para profesionales del sector
            </p>
          </div>

          <div className="mt-16 grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
            {/* Feature 1 */}
            <div className="card-hover rounded-xl border border-border bg-white p-6">
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-brand-50">
                <Zap className="h-6 w-6 text-brand-500" />
              </div>
              <h3 className="mt-4 text-lg font-semibold">Chat IA Experto</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Pregunta sobre normativas, resoluciones y operación del mercado.
                Respuestas con citaciones de fuentes oficiales.
              </p>
            </div>

            {/* Feature 2 */}
            <div className="card-hover rounded-xl border border-border bg-white p-6">
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-accent-50">
                <Search className="h-6 w-6 text-accent-500" />
              </div>
              <h3 className="mt-4 text-lg font-semibold">Búsqueda Normativa</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Encuentra leyes, decretos, resoluciones y normas técnicas en
                segundos. Siempre actualizado.
              </p>
            </div>

            {/* Feature 3 */}
            <div className="card-hover rounded-xl border border-border bg-white p-6">
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-success-light">
                <BarChart3 className="h-6 w-6 text-success" />
              </div>
              <h3 className="mt-4 text-lg font-semibold">Dashboard en Vivo</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Costos marginales, generación y demanda del SEN. Datos
                actualizados cada hora.
              </p>
            </div>

            {/* Feature 4 */}
            <div className="card-hover rounded-xl border border-border bg-white p-6">
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-warning-light">
                <Bell className="h-6 w-6 text-warning" />
              </div>
              <h3 className="mt-4 text-lg font-semibold">Alertas Inteligentes</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Recibe notificaciones de cambios regulatorios, nuevos documentos
                y umbrales de precios.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <section id="pricing" className="bg-muted/30 py-24">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
              Precios simples y transparentes
            </h2>
            <p className="mt-4 text-lg text-muted-foreground">
              6-12x más económico que las alternativas tradicionales
            </p>
          </div>

          <div className="mt-16 grid gap-8 lg:grid-cols-3">
            {/* Starter */}
            <div className="rounded-xl border border-border bg-white p-8">
              <h3 className="text-lg font-semibold">Starter</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Para profesionales independientes
              </p>
              <div className="mt-6">
                <span className="text-4xl font-bold">$99</span>
                <span className="text-muted-foreground"> USD/mes</span>
              </div>
              <ul className="mt-8 space-y-3 text-sm">
                <li className="flex items-center gap-2">
                  <span className="text-success">✓</span> 500 consultas/mes
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-success">✓</span> Chat IA con fuentes
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-success">✓</span> Búsqueda normativa
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-success">✓</span> Alertas básicas
                </li>
              </ul>
              <Link
                href="/signup?plan=starter"
                className="mt-8 block w-full rounded-lg border border-brand-500 py-2.5 text-center font-medium text-brand-500 transition-colors hover:bg-brand-50"
              >
                Comenzar prueba
              </Link>
            </div>

            {/* Professional - Highlighted */}
            <div className="relative rounded-xl border-2 border-brand-500 bg-white p-8 shadow-lg">
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-brand-500 px-3 py-1 text-xs font-medium text-white">
                Más popular
              </div>
              <h3 className="text-lg font-semibold">Professional</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Para equipos pequeños
              </p>
              <div className="mt-6">
                <span className="text-4xl font-bold">$199</span>
                <span className="text-muted-foreground"> USD/mes</span>
              </div>
              <ul className="mt-8 space-y-3 text-sm">
                <li className="flex items-center gap-2">
                  <span className="text-success">✓</span> 2,000 consultas/mes
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-success">✓</span> Todo de Starter
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-success">✓</span> Dashboard completo
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-success">✓</span> Exportación de datos
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-success">✓</span> 3 usuarios
                </li>
              </ul>
              <Link
                href="/signup?plan=professional"
                className="mt-8 block w-full rounded-lg bg-brand-500 py-2.5 text-center font-medium text-white transition-colors hover:bg-brand-600"
              >
                Comenzar prueba
              </Link>
            </div>

            {/* Business */}
            <div className="rounded-xl border border-border bg-white p-8">
              <h3 className="text-lg font-semibold">Business</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Para empresas del sector
              </p>
              <div className="mt-6">
                <span className="text-4xl font-bold">$399</span>
                <span className="text-muted-foreground"> USD/mes</span>
              </div>
              <ul className="mt-8 space-y-3 text-sm">
                <li className="flex items-center gap-2">
                  <span className="text-success">✓</span> 10,000 consultas/mes
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-success">✓</span> Todo de Professional
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-success">✓</span> Inteligencia
                  competitiva
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-success">✓</span> Reportes
                  personalizados
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-success">✓</span> 10 usuarios
                </li>
              </ul>
              <Link
                href="/signup?plan=business"
                className="mt-8 block w-full rounded-lg border border-brand-500 py-2.5 text-center font-medium text-brand-500 transition-colors hover:bg-brand-50"
              >
                Comenzar prueba
              </Link>
            </div>
          </div>

          <p className="mt-8 text-center text-sm text-muted-foreground">
            ¿Necesitas más? Contáctanos para un plan Enterprise personalizado.
          </p>
        </div>
      </section>

      {/* CTA Section */}
      <section className="bg-brand-500 py-16">
        <div className="mx-auto max-w-7xl px-4 text-center sm:px-6 lg:px-8">
          <h2 className="text-3xl font-bold tracking-tight text-white">
            Comienza hoy, gratis por 14 días
          </h2>
          <p className="mt-4 text-lg text-brand-100">
            Sin tarjeta de crédito. Sin compromisos. Cancela cuando quieras.
          </p>
          <Link
            href="/signup"
            className="mt-8 inline-flex items-center gap-2 rounded-lg bg-white px-6 py-3 font-medium text-brand-500 transition-colors hover:bg-brand-50"
          >
            Crear cuenta gratis
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border bg-white py-12">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
            <div className="flex items-center gap-2">
              <Zap className="h-6 w-6 text-brand-500" />
              <span className="font-bold">ELECTRIA</span>
            </div>
            <p className="text-sm text-muted-foreground">
              © 2026 ELECTRIA. Todos los derechos reservados.
            </p>
            <div className="flex gap-6">
              <Link
                href="/privacy"
                className="text-sm text-muted-foreground hover:text-foreground"
              >
                Privacidad
              </Link>
              <Link
                href="/terms"
                className="text-sm text-muted-foreground hover:text-foreground"
              >
                Términos
              </Link>
            </div>
          </div>
        </div>
      </footer>
    </main>
  );
}
