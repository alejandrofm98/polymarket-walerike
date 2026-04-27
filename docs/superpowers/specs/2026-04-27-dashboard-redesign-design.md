# Diseño de Rediseño del Dashboard Frontend

## 1. Propósito y Objetivos
El objetivo de este rediseño es transformar la interfaz actual (centrada en tablas densas) en un dashboard moderno, enfocado y visualmente atractivo. Se prioriza la lectura rápida de la rentabilidad global (Cuenta) y la evaluación intuitiva del estado de los mercados, eliminando datos crudos innecesarios.

## 2. Arquitectura de UI y Layout
El dashboard abandonará el esquema tradicional de tablas en favor de un enfoque **"Bento Box" + "Hero Panel"**.

*   **Hero Panel (Cuenta y Estado Global):**
    *   Ubicado en la parte superior.
    *   Mostrará en tipografía de gran tamaño el Saldo de la cuenta (`account.available` / `balance`) y el PnL.
    *   Incluirá un resumen sutil del estado del bot o el último log crítico.
*   **Bento Grid (Mercados):**
    *   Una cuadrícula responsiva (CSS Grid) debajo del Hero Panel.
    *   Contendrá tarjetas individuales (`MarketCard`) para cada mercado.
    *   El tamaño de las tarjetas puede variar ligeramente para romper la monotonía visual, pero manteniendo alineación.

## 3. Componentes Clave

### 3.1 `AccountHeroPanel`
Reemplaza al antiguo `AccountView` en su formato de tarjeta estándar.
*   **Datos:** Saldo total, ganancias/pérdidas, estado de conexión (Errores si los hay).
*   **Visual:** Fondo sutilmente coloreado según el estado del PnL (verde/rojo muy translúcido), texto principal destacado (text-4xl o similar).

### 3.2 `MarketCard` (Reemplaza a `MarketsTable`)
En lugar de una fila de tabla con 10 columnas, cada mercado es una tarjeta.
*   **Datos Conservados:**
    *   Título del mercado (Pregunta).
    *   Target vs Current (como contexto secundario).
    *   YES/NO Probabilidades (transformadas visualmente).
    *   Net Edge (transformado en un badge).
*   **Datos Eliminados / Transformados:**
    *   `Diff`: Se elimina el número. Se cambia por texto amigable (ej. "A $200 de distancia").
    *   `Timeframe`: Pasa a ser un pequeño 'tag' junto al símbolo del Asset en la esquina superior.
*   **Representación Visual:**
    *   **Barra de Probabilidad:** Una barra horizontal donde el porcentaje de "YES" domina un color y el "NO" el restante.
    *   **Badge de Edge:** En lugar de `Edge: 2.5%`, usar un badge: `<Badge className="bg-emerald-500/20 text-emerald-400">Buen Edge</Badge>` (o neutro si es bajo).

## 4. Estilo y Estética
*   **Paleta de colores:** Mantener el tema oscuro actual, pero potenciar el contraste. Uso intensivo de `bg-white/[0.02]`, bordes `border-white/5` a `border-white/10`.
*   **Tipografía:** Fuentes sin serif modernas, utilizando jerarquía extrema (pesos `bold` / `extrabold` para números clave, `text-muted-foreground` y textos diminutos para labels).
*   **Espaciado (Negativo):** Paddings generosos (`p-6` o `p-8` en tarjetas grandes) para respirar.

## 5. Manejo de Estado y Datos
*   La capa de datos (`types.ts`, hooks actuales, websockets en `bot_engine.py`) **no cambiará**. El rediseño es puramente de presentación (Frontend).
*   Se seguirán utilizando los props actuales (`markets: Market[]`, `account: AccountSummary`) que se inyectarán en los nuevos componentes.

## 6. Fases de Implementación
1.  Crear el `AccountHeroPanel` usando los datos de `AccountSummary`.
2.  Desarrollar el componente individual `MarketCard` con la lógica visual de barras y badges.
3.  Ensamblar el `MarketsBentoGrid` que mapee el array de `markets` renderizando `MarketCard`s.
4.  Reemplazar las vistas antiguas en `App.tsx` / `Dashboard` por la nueva jerarquía.