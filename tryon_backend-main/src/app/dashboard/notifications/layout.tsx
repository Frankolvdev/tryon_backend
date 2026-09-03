"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import {
  Bell,
  ChevronRight,
  Megaphone,
  RadioTower,
  Settings2,
} from "lucide-react";

import { cn } from "@/lib/utils";

interface NotificationsLayoutProps {
  children: ReactNode;
}

const sections = [
  {
    label: "Centro",
    description:
      "Avisos administrativos, prioridades y acciones pendientes.",
    href: "/dashboard/notifications",
    icon: Bell,
  },
  {
    label: "Preferencias y canales",
    description:
      "Horarios silenciosos, prioridad mínima y destinos externos.",
    href: "/dashboard/notifications/preferences",
    icon: Settings2,
  },
  {
    label: "Entregas",
    description:
      "Intentos, errores del proveedor y reintentos de envío.",
    href: "/dashboard/notifications/deliveries",
    icon: RadioTower,
  },
  {
    label: "Anuncios",
    description:
      "Publica avisos globales para los usuarios finales.",
    href: "/dashboard/notifications/announcements",
    icon: Megaphone,
  },
] as const;

function isActive(
  pathname: string,
  href: string,
): boolean {
  if (href === "/dashboard/notifications") {
    return pathname === href;
  }

  return (
    pathname === href ||
    pathname.startsWith(`${href}/`)
  );
}

export default function NotificationsLayout({
  children,
}: NotificationsLayoutProps) {
  const pathname = usePathname();
  const showQuickAccess =
    pathname === "/dashboard/notifications";

  const activeSection =
    sections.find((section) =>
      isActive(pathname, section.href),
    ) ?? sections[0];

  return (
    <div>
      <nav
        aria-label="Secciones de notificaciones"
        className="luxia-panel mb-5 rounded-3xl p-3"
      >
        <div className="flex gap-2 overflow-x-auto">
          {sections.map((section) => {
            const Icon = section.icon;
            const active = isActive(
              pathname,
              section.href,
            );

            return (
              <Link
                key={section.href}
                href={section.href}
                className={cn(
                  "inline-flex h-11 shrink-0 items-center gap-2 rounded-xl px-4 text-sm transition",
                  active
                    ? "border border-red-500/20 bg-red-950/25 font-semibold text-red-300"
                    : "border border-transparent text-zinc-600 hover:border-white/7 hover:bg-white/[0.025] hover:text-zinc-300",
                )}
              >
                <Icon size={16} />
                {section.label}
              </Link>
            );
          })}
        </div>
      </nav>

      <div className="mb-5 flex flex-wrap items-center gap-2 px-1 text-xs text-zinc-700">
        <Link
          href="/dashboard"
          className="transition hover:text-zinc-300"
        >
          Dashboard
        </Link>

        <ChevronRight size={13} />

        <Link
          href="/dashboard/notifications"
          className="transition hover:text-zinc-300"
        >
          Notificaciones
        </Link>

        {activeSection.href !==
          "/dashboard/notifications" && (
          <>
            <ChevronRight size={13} />
            <span className="text-zinc-500">
              {activeSection.label}
            </span>
          </>
        )}
      </div>

      {showQuickAccess && (
        <section className="mb-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {sections.map((section) => {
            const Icon = section.icon;

            return (
              <Link
                key={section.href}
                href={section.href}
                className="luxia-panel group rounded-2xl p-5 transition hover:-translate-y-0.5 hover:border-red-500/15"
              >
                <div className="flex size-10 items-center justify-center rounded-xl border border-red-500/15 bg-red-950/15 text-red-400">
                  <Icon size={18} />
                </div>

                <h2 className="mt-4 text-sm font-semibold text-white">
                  {section.label}
                </h2>

                <p className="mt-2 text-xs leading-5 text-zinc-600">
                  {section.description}
                </p>

                <span className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-red-400">
                  Abrir
                  <ChevronRight
                    size={13}
                    className="transition group-hover:translate-x-0.5"
                  />
                </span>
              </Link>
            );
          })}
        </section>
      )}

      {children}
    </div>
  );
}
