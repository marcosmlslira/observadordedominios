'use client';

import React, { useState, useEffect } from 'react';
import { FoundationsSection } from './sections/FoundationsSection';
import { ComponentsSection } from './sections/ComponentsSection';
import { ThemeToggle } from '@/components/theme-toggle';

export default function DesignSystemPage() {
  const [activeSection, setActiveSection] = useState('');

  const navigationItems = [
    {
      title: 'Foundations',
      id: 'foundations',
      subitems: [
        { title: 'Typography', id: 'typography' },
        { title: 'Colors', id: 'colors' },
        { title: 'Spacing', id: 'spacing' },
        { title: 'Border Radius', id: 'border-radius' },
        { title: 'Shadows', id: 'shadows' },
        { title: 'Motion', id: 'motion' },
      ],
    },
    {
      title: 'Components',
      id: 'components',
      subitems: [
        { title: 'Buttons', id: 'buttons' },
        { title: 'Inputs', id: 'inputs' },
        { title: 'Selectors', id: 'selectors' },
        { title: 'Badges', id: 'badges' },
        { title: 'Navigation', id: 'navigation' },
        { title: 'Cards', id: 'cards' },
        { title: 'Tables', id: 'tables' },
        { title: 'Overlays', id: 'overlays' },
        { title: 'Feedback', id: 'feedback' },
        { title: 'User & Access', id: 'user-access' },
        { title: 'Loading States', id: 'loading-states' },
        { title: 'Empty State', id: 'empty-state' },
      ],
    },
  ];

  useEffect(() => {
    const handleScroll = () => {
      const sections = navigationItems.flatMap(item => [
        { id: item.id },
        ...item.subitems
      ]);

      for (const section of sections) {
        const element = document.getElementById(section.id);
        if (element) {
          const rect = element.getBoundingClientRect();
          if (rect.top >= 0 && rect.top <= 200) {
            setActiveSection(section.id);
            break;
          }
        }
      }
    };

    window.addEventListener('scroll', handleScroll);
    handleScroll();
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const scrollToSection = (id: string) => {
    const element = document.getElementById(id);
    if (element) {
      const offset = 20;
      const elementPosition = element.getBoundingClientRect().top + window.scrollY;
      window.scrollTo({
        top: elementPosition - offset,
        behavior: 'smooth',
      });
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <ThemeToggle />
      {/* Header */}
      <header className="border-b border-border bg-card">
        <div className="container mx-auto px-4 py-6">
          <h1 className="text-4xl font-bold text-foreground">Design System</h1>
          <p className="text-muted-foreground mt-2">
            Catálogo completo de componentes, tokens e padrões visuais
          </p>
        </div>
      </header>

      <div className="flex">
        {/* Sidebar Navigation */}
        <aside className="w-64 border-r border-border bg-card/50 sticky top-0 h-screen overflow-y-auto">
          <nav className="p-4 space-y-1">
            {navigationItems.map((section) => (
              <div key={section.id} className="space-y-1">
                <button
                  onClick={() => scrollToSection(section.id)}
                  className={`w-full text-left px-3 py-2 text-sm font-semibold rounded-md transition-colors ${
                    activeSection === section.id
                      ? 'bg-primary text-primary-foreground'
                      : 'text-foreground hover:bg-muted'
                  }`}
                >
                  {section.title}
                </button>
                <div className="ml-4 space-y-1">
                  {section.subitems.map((item) => (
                    <button
                      key={item.id}
                      onClick={() => scrollToSection(item.id)}
                      className={`w-full text-left px-3 py-1.5 text-sm rounded-md transition-colors ${
                        activeSection === item.id
                          ? 'bg-muted text-primary font-medium'
                          : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                      }`}
                    >
                      {item.title}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </nav>
        </aside>

        {/* Main Content */}
        <main className="flex-1 px-8 py-8 space-y-16">
          {/* Foundations */}
          <FoundationsSection />

          {/* Components */}
          <ComponentsSection />

          {/* Footer */}
          <footer className="border-t border-border mt-16 pt-8">
            <div className="text-center text-sm text-muted-foreground">
              <p>🔒 Esta página está disponível apenas em ambiente de desenvolvimento</p>
              <p className="mt-2">
                <strong>Regra de Ouro:</strong> Se um componente não aparece aqui, ele não existe.
              </p>
            </div>
          </footer>
        </main>
      </div>
    </div>
  );
}
