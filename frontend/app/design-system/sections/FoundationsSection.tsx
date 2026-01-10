'use client';

import React from 'react';

export function FoundationsSection() {
  const baseColors = [
    { name: 'Background', token: '--background', usage: 'Fundo principal da aplicação', swatchClass: 'bg-background' },
    { name: 'Foreground', token: '--foreground', usage: 'Texto principal', swatchClass: 'bg-foreground' },
  ];

  const brandColors = [
    { name: 'Primary', token: '--primary', usage: 'CTA principal, ações primárias (bg-primary + text-primary-foreground)', swatchClass: 'bg-primary' },
    { name: 'Brand Brown 700', token: '--brand-brown-700', usage: 'Identidade estrutural (header/sidebar)', swatchClass: 'bg-brandBrown-700' },
    { name: 'Brand Brown 900', token: '--brand-brown-900', usage: 'Identidade estrutural (header/sidebar)', swatchClass: 'bg-brandBrown-900' },
    { name: 'Brand Yellow 500', token: '--brand-yellow-500', usage: 'Focus ring e atenção pontual (nunca como fundo grande)', swatchClass: 'bg-brandYellow-500' },
  ];

  const neutralColors = [
    { name: 'Muted', token: '--muted', usage: 'Superfícies secundárias, disabled, backgrounds sutis', swatchClass: 'bg-muted' },
    { name: 'Muted Foreground', token: '--muted-foreground', usage: 'Texto secundário e descrições', swatchClass: 'bg-muted-foreground' },
  ];

  const borderColors = [
    { name: 'Border Subtle', token: '--border-subtle', usage: 'Divisores leves', swatchClass: 'bg-border-subtle' },
    { name: 'Border Default', token: '--border', usage: 'Cards e inputs', swatchClass: 'bg-border' },
    { name: 'Border Strong', token: '--border-strong', usage: 'Outline buttons e estados ativos', swatchClass: 'bg-border-strong' },
  ];

  const semanticColors = [
    { name: 'Success', token: '--success', usage: 'Feedback positivo (bg-success + text-success-foreground)', swatchClass: 'bg-success' },
    { name: 'Warning', token: '--warning', usage: 'Avisos e atenção (diferente do Brand Yellow)', swatchClass: 'bg-warning' },
    { name: 'Error / Danger', token: '--error', usage: 'Erros e ações destrutivas (bg-destructive + text-destructive-foreground)', swatchClass: 'bg-error' },
    { name: 'Info', token: '--info', usage: 'Mensagens informativas', swatchClass: 'bg-info' },
  ];

  const contextualColors = [
    { name: 'DNS', token: '--dns', usage: 'Monitoramento de DNS', bg: 'bg-dns', text: 'text-dns' },
    { name: 'Uptime', token: '--uptime', usage: 'Status de disponibilidade', bg: 'bg-uptime', text: 'text-uptime' },
    { name: 'SSL', token: '--ssl', usage: 'Certificados SSL/TLS', bg: 'bg-ssl', text: 'text-ssl' },
    { name: 'Blacklist', token: '--blacklist', usage: 'Status de blacklist', bg: 'bg-blacklist', text: 'text-blacklist' },
    { name: 'Billing', token: '--billing', usage: 'Faturamento e pagamentos', bg: 'bg-billing', text: 'text-billing' },
  ];

  const typographyExamples = [
    { name: 'Heading 1', class: 'text-5xl font-bold', text: 'The quick brown fox' },
    { name: 'Heading 2', class: 'text-4xl font-bold', text: 'The quick brown fox' },
    { name: 'Heading 3', class: 'text-3xl font-semibold', text: 'The quick brown fox' },
    { name: 'Heading 4', class: 'text-2xl font-semibold', text: 'The quick brown fox' },
    { name: 'Body Large', class: 'text-lg font-normal', text: 'The quick brown fox jumps over the lazy dog' },
    { name: 'Body Normal', class: 'text-base font-normal', text: 'The quick brown fox jumps over the lazy dog' },
    { name: 'Body Small', class: 'text-sm font-normal', text: 'The quick brown fox jumps over the lazy dog' },
    { name: 'Caption', class: 'text-xs font-normal text-muted-foreground', text: 'The quick brown fox jumps over the lazy dog' },
    { name: 'Code', class: 'text-sm font-mono bg-muted px-1 rounded', text: 'const hello = "world";' },
  ];

  const spacingScale = [
    { name: 'xs', value: '0.5', pixels: '2px', widthClass: 'w-0.5' },
    { name: 'sm', value: '1', pixels: '4px', widthClass: 'w-1' },
    { name: 'md', value: '2', pixels: '8px', widthClass: 'w-2' },
    { name: 'lg', value: '4', pixels: '16px', widthClass: 'w-4' },
    { name: 'xl', value: '6', pixels: '24px', widthClass: 'w-6' },
    { name: '2xl', value: '8', pixels: '32px', widthClass: 'w-8' },
    { name: '3xl', value: '12', pixels: '48px', widthClass: 'w-12' },
    { name: '4xl', value: '16', pixels: '64px', widthClass: 'w-16' },
  ];

  const borderRadii = [
    { name: 'none', class: 'rounded-none', value: '0px' },
    { name: 'sm', class: 'rounded-sm', value: '2px' },
    { name: 'md', class: 'rounded-md', value: '6px' },
    { name: 'lg', class: 'rounded-lg', value: '8px' },
    { name: 'xl', class: 'rounded-xl', value: '12px' },
    { name: '2xl', class: 'rounded-2xl', value: '16px' },
    { name: 'full', class: 'rounded-full', value: '9999px' },
  ];

  const shadows = [
    { name: 'sm', class: 'shadow-sm', description: 'Elevação sutil' },
    { name: 'md', class: 'shadow-md', description: 'Elevação padrão' },
    { name: 'lg', class: 'shadow-lg', description: 'Elevação alta' },
    { name: 'xl', class: 'shadow-xl', description: 'Elevação máxima' },
  ];

  return (
    <section id="foundations" className="space-y-12">
      <div>
        <h2 className="text-3xl font-bold text-foreground mb-2">Foundations</h2>
        <p className="text-muted-foreground">
          Tokens fundamentais que definem a identidade visual
        </p>
      </div>

      {/* Typography */}
      <div id="typography" className="space-y-6">
        <div>
          <h3 className="text-2xl font-semibold text-foreground mb-4">Typography</h3>
          <div className="space-y-4">
            {typographyExamples.map((example) => (
              <div key={example.name} className="border border-border rounded-lg p-4 bg-card">
                <div className="flex items-baseline justify-between mb-2">
                  <span className="text-sm font-medium text-muted-foreground">{example.name}</span>
                  <code className="text-xs text-muted-foreground bg-muted px-2 py-1 rounded">
                    {example.class}
                  </code>
                </div>
                <div className={example.class}>{example.text}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Colors */}
      <div id="colors" className="space-y-6">
        <div>
          <h3 className="text-2xl font-semibold text-foreground mb-4">Colors</h3>

          <div className="space-y-8">
            <div>
              <h4 className="text-xl font-semibold text-foreground mb-4">Base</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {baseColors.map((color) => (
                  <div key={color.name} className="border border-border rounded-lg p-4 bg-card">
                    <div className={`h-16 rounded-md mb-3 ${color.swatchClass}`} />
                    <h5 className="font-semibold text-foreground mb-1">{color.name}</h5>
                    <code className="text-xs text-muted-foreground block mb-2">{color.token}</code>
                    <p className="text-sm text-muted-foreground">{color.usage}</p>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h4 className="text-xl font-semibold text-foreground mb-4">Marca</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {brandColors.map((color) => (
                  <div key={color.name} className="border border-border rounded-lg p-4 bg-card">
                    <div className={`h-16 rounded-md mb-3 ${color.swatchClass}`} />
                    <h5 className="font-semibold text-foreground mb-1">{color.name}</h5>
                    <code className="text-xs text-muted-foreground block mb-2">{color.token}</code>
                    <p className="text-sm text-muted-foreground">{color.usage}</p>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h4 className="text-xl font-semibold text-foreground mb-4">Neutros</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {neutralColors.map((color) => (
                  <div key={color.name} className="border border-border rounded-lg p-4 bg-card">
                    <div className={`h-16 rounded-md mb-3 ${color.swatchClass}`} />
                    <h5 className="font-semibold text-foreground mb-1">{color.name}</h5>
                    <code className="text-xs text-muted-foreground block mb-2">{color.token}</code>
                    <p className="text-sm text-muted-foreground">{color.usage}</p>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h4 className="text-xl font-semibold text-foreground mb-4">Bordas</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {borderColors.map((color) => (
                  <div key={color.name} className="border border-border rounded-lg p-4 bg-card">
                    <div className={`h-16 rounded-md mb-3 ${color.swatchClass}`} />
                    <h5 className="font-semibold text-foreground mb-1">{color.name}</h5>
                    <code className="text-xs text-muted-foreground block mb-2">{color.token}</code>
                    <p className="text-sm text-muted-foreground">{color.usage}</p>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h4 className="text-xl font-semibold text-foreground mb-4">Estados Semânticos</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {semanticColors.map((color) => (
                  <div key={color.name} className="border border-border rounded-lg p-4 bg-card">
                    <div className={`h-16 rounded-md mb-3 ${color.swatchClass}`} />
                    <h5 className="font-semibold text-foreground mb-1">{color.name}</h5>
                    <code className="text-xs text-muted-foreground block mb-2">{color.token}</code>
                    <p className="text-sm text-muted-foreground">{color.usage}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Contextual Colors - OBS Domínios */}
        <div className="mt-8">
          <h4 className="text-xl font-semibold text-foreground mb-4">Cores Contextuais (OBS Domínios)</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {contextualColors.map((color) => (
              <div key={color.name} className="border border-border rounded-lg p-4 bg-card">
                <div className={`h-16 rounded-md mb-3 ${color.bg}`} />
                <h4 className="font-semibold text-foreground mb-1">{color.name}</h4>
                <code className="text-xs text-muted-foreground block mb-2">{color.token}</code>
                <p className="text-sm text-muted-foreground mb-2">{color.usage}</p>
                <div className="flex gap-2 text-xs">
                  <code className="bg-muted px-1 rounded">{color.bg}</code>
                  <code className="bg-muted px-1 rounded">{color.text}</code>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Spacing */}
      <div id="spacing" className="space-y-6">
        <div>
          <h3 className="text-2xl font-semibold text-foreground mb-4">Spacing</h3>
          <div className="space-y-3">
            {spacingScale.map((space) => (
              <div key={space.name} className="border border-border rounded-lg p-4 bg-card">
                <div className="flex items-center gap-4">
                  <div className="shrink-0 w-24">
                    <span className="text-sm font-medium text-foreground">{space.name}</span>
                    <code className="text-xs text-muted-foreground block">{space.pixels}</code>
                  </div>
                  <div className={`h-8 bg-primary rounded ${space.widthClass}`} />
                  <code className="text-xs text-muted-foreground">space-{space.value}</code>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Border Radius */}
      <div id="border-radius" className="space-y-6">
        <div>
          <h3 className="text-2xl font-semibold text-foreground mb-4">Border Radius</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {borderRadii.map((radius) => (
              <div key={radius.name} className="border border-border rounded-lg p-4 bg-card">
                <div
                  className={`h-16 w-16 bg-primary mb-3 ${radius.class}`}
                />
                <h4 className="font-semibold text-foreground text-sm">{radius.name}</h4>
                <code className="text-xs text-muted-foreground block">{radius.class}</code>
                <span className="text-xs text-muted-foreground">{radius.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Shadows (Elevation) */}
      <div id="shadows" className="space-y-6">
        <div>
          <h3 className="text-2xl font-semibold text-foreground mb-4">Elevation (Shadows)</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {shadows.map((shadow) => (
              <div key={shadow.name} className="space-y-3">
                <div className={`h-24 bg-card border border-border rounded-lg ${shadow.class}`} />
                <div>
                  <h4 className="font-semibold text-foreground text-sm">{shadow.name}</h4>
                  <code className="text-xs text-muted-foreground block">{shadow.class}</code>
                  <p className="text-xs text-muted-foreground mt-1">{shadow.description}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Motion */}
      <div id="motion" className="space-y-6">
        <div>
          <h3 className="text-2xl font-semibold text-foreground mb-4">Motion</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="border border-border rounded-lg p-6 bg-card space-y-4">
              <h4 className="font-semibold text-foreground">Fast</h4>
              <code className="text-xs text-muted-foreground block">duration-75 (75ms)</code>
              <div className="h-12 bg-primary rounded transition-all duration-75 hover:translate-x-4" />
              <p className="text-xs text-muted-foreground">Hover para ver a animação</p>
            </div>
            <div className="border border-border rounded-lg p-6 bg-card space-y-4">
              <h4 className="font-semibold text-foreground">Base</h4>
              <code className="text-xs text-muted-foreground block">duration-150 (150ms)</code>
              <div className="h-12 bg-primary rounded transition-all duration-150 hover:translate-x-4" />
              <p className="text-xs text-muted-foreground">Hover para ver a animação</p>
            </div>
            <div className="border border-border rounded-lg p-6 bg-card space-y-4">
              <h4 className="font-semibold text-foreground">Slow</h4>
              <code className="text-xs text-muted-foreground block">duration-300 (300ms)</code>
              <div className="h-12 bg-primary rounded transition-all duration-300 hover:translate-x-4" />
              <p className="text-xs text-muted-foreground">Hover para ver a animação</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
