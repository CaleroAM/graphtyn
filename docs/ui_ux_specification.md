# 🎨 Especificación UI/UX de Graphtyn

**Versión:** 1.0.0  
**Proyecto:** Graphtyn (`graphtyn`)
**Ruta:** `/home/developer/Documentos/docker/PROYECTOS/graphtyn`
**Estado:** Propuesta de Diseño y Especificación de Interfaz  

---

## 1. Resumen Ejecutivo y Objetivos

Graphtyn es un motor de contexto determinista basado en AST y topología de agentes de IA para proyectos de desarrollo de software. Esta especificación define la evolución de la interfaz visual web (puerto `9210`), transformándola en un dashboard moderno, responsivo y de alto impacto visual con soporte para exploración de código y gobernanza de agentes en tiempo real.

### Objetivos Clave de UI/UX:
1. **Navegación Multiproyecto (Barra Lateral Izquierda):** Permitir al usuario explorar múltiples repositorios indexados, ver el estado de salud del AST y ejecutar reindexaciones bajo demanda con retroalimentación visual clara.
2. **Conmutación Dual de Vistas (AST Code Graph vs. Agent Harness Topology):** Habilitar el cambio fluido entre la estructura estática del código fuente y la topología dinámica del arnés de agentes autónomos.
3. **Optimización Extrema de Contraste y Brillo en Conectores de Grafo:** Eliminar líneas oscuras o ilegibles sobre fondo oscuro (`#0b0d12`), implementando efectos de resplandor neón (*bioluminescent glow*), gradientes de relación cromática y animaciones de partículas de flujo de datos.

---

## 2. Maquetas y Wireframes Visuales

### 2.1 Vista Principal: Grafo AST de Código y Barra Lateral Izquierda
![Graphtyn Main AST Graph UI](/home/developer/.gemini/antigravity-cli/brain/f567f07f-7a33-46ad-a9c8-d2a8d6f4d746/graphtyn_ui_main_1785948974624.jpg)

### 2.2 Vista Alternativa: Topología de Agentes del Arnés (Agent Harness Topology)
![Graphtyn Agent Harness Topology UI](/home/developer/.gemini/antigravity-cli/brain/f567f07f-7a33-46ad-a9c8-d2a8d6f4d746/graphtyn_agent_topology_1785948987795.jpg)

---

## 3. Especificación Detallada por Componentes

```
+-----------------------------------------------------------------------------------+
|  [🌌 Graphtyn]       [ 📈 Project AST Graph ]  [ 🤖 Agent Harness Topology ]   |
+------------------------+----------------------------------------------------------+
|  Proyectos Indexados   |                                                          |
|                        |                  CANVAS DE GRAFO 3D/2D                  |
|  🟢 NovaCore-Engine    |                                                          |
|  🟢 HydraX_Services    |                (Nodos con Resplandor Neón                |
|  🟢 QuantumParser      |                 y Conectores de Alto                    |
|  🔴 Orion_UI_Kit       |                     Contraste)                           |
|                        |                                                          |
|                        |                                                          |
|                        |                                     +------------------+ |
|                        |                                     | Panel de Detalles| |
|                        |                                     | Symbol / Agent   | |
|  +------------------+  |                                     +------------------+ |
|  | 🔄 REINDEXAR     |  |                                                          |
|  +------------------+  |                                                          |
+------------------------+----------------------------------------------------------+
```

### 3.1 Barra Lateral Izquierda (Sidebar Panel)
* **Ancho Fijo:** `260px` (plegable a `64px` en pantallas compactas).
* **Fondo:** `rgba(15, 23, 42, 0.95)` con filtro `backdrop-filter: blur(16px)` y borde derecho `1px solid rgba(148, 163, 184, 0.12)`.
* **Elementos:**
  * **Cabecera de Lista:** Título "Proyectos Indexados" con contador badge (ej. `4 Activos`).
  * **Lista de Proyectos (`ProjectListItem`):**
    * Muestra nombre del proyecto, indicador de estado (`🟢 Indexado`, `🟡 Indexando...`, `🔴 Error AST`).
    * Al hacer clic, envía evento `switchProject(projectId)` y recarga los datos del grafo vía `/api/graph?project={id}`.
  * **Botón 'Reindexar' (`ReindexButton`):**
    * **Ubicación:** Anclado en la parte inferior del sidebar (`position: sticky; bottom: 0`).
    * **Estilo Visual:** Botón violeta radiante (`background: linear-gradient(135deg, #6366f1, #8b5cf6)`), sombra con brillo `box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4)`.
    * **Estado Activo/Loading:** Al presionar, muestra un spinner dinámico y deshabilita el botón mientras llama a la API `/api/reindex`.

### 3.2 Conmutador de Vistas (Header View Switcher Tabs)
* **Ubicación:** En la barra superior (Header Navigation Bar).
* **Segmented Control Tabs:**
  1. **`Project AST Graph`:** Muestra la estructura sintáctica del código fuente (Archivos, Clases, Funciones, Llamadas).
  2. **`Agent Harness Topology`:** Muestra la arquitectura del sistema multi-agente en ejecución (Supervisor, Code Parser, Test Runner, Memory Store).
* **Estilo de Pestaña Activa:** Borde inferior brillante `#00f0ff` (Cyan) o `#8b5cf6` (Violeta), fondo semitransparente `rgba(56, 189, 248, 0.12)` e icono resaltado.

### 3.3 Sistema de Conectores de Alto Contraste y Brillo (High-Contrast Graph Edges)
Para resolver la problemática de los conectores oscuros e invisibles:
* **Paleta Cromática Neón por Tipo de Relación:**
  * `IMPORTS` (Dependencia de Archivo): Cyan Eléctrico `#00f0ff` (`rgba(0, 240, 255, 0.85)`).
  * `INHERITS` (Herencia de Clase): Magenta Neón `#ff007f` (`rgba(255, 0, 127, 0.85)`).
  * `CALLS` (Llamada a Función): Púrpura Radiante `#a855f7` (`rgba(168, 85, 247, 0.85)`).
  * `AGENT_CHANNEL` (Bus Inter-Agente): Verde Lima Neón `#10b981` / Ámbar `#f59e0b`.
* **Mejoras Tecnológicas de Renderizado:**
  * **Ancho de Línea:** Aumento del grosor base a `2.5px` en 2D / `1.8px` en 3D.
  * **Material Resplandeciente (Bloom / Glow Effect):**
    * En WebGL (`3d-force-graph`): Uso de `MeshBasicMaterial` o shaders con emisión de luz `emissive: 0x00f0ff` y pase post-procesamiento de Bloom.
    * En Canvas/SVG 2D: Aplicación de `ctx.shadowBlur = 8` y `ctx.shadowColor = link.color`.
  * **Partículas de Flujo Animadas (`Link directional particles`):**
    * Partículas brillantes desplazándose a lo largo del conector para indicar dirección del flujo de datos o invocaciones (`linkColor`, `linkDirectionalParticles={3}`, `linkDirectionalParticleSpeed={0.008}`).

---

## 4. Arquitectura de UI y Cambios de Código Sugeridos

Para actualizar `graphtyn/api/main.py` con esta especificación UI/UX:

```html
<!-- Fragmento HTML/CSS del Sidebar y Tabs en index() -->
<div id="app-layout">
  <aside id="sidebar">
    <div class="sidebar-header">
      <h3>📁 Repositorios</h3>
    </div>
    <ul id="project-list">
      <li class="active"><span class="status-dot online"></span> NovaCore-Engine</li>
      <li><span class="status-dot online"></span> HydraX_Services</li>
      <li><span class="status-dot online"></span> QuantumParser</li>
    </ul>
    <button id="btn-reindex" onclick="triggerReindex()">
      <span class="icon">🔄</span> Reindexar Proyecto
    </button>
  </aside>

  <main id="main-content">
    <header id="top-nav">
      <div class="view-tabs">
        <button class="tab-btn active" onclick="switchView('ast')">📊 Project AST Graph</button>
        <button class="tab-btn" onclick="switchView('harness')">🤖 Agent Harness Topology</button>
      </div>
    </header>

    <div id="graph-container"></div>
  </main>
</div>
```

---

## 5. Matriz de Colores y Tokens UI

| Componente | Token CSS / Valor Hex | Descripción |
| :--- | :--- | :--- |
| **Fondo Principal** | `#0b0d12` | Negro azulado profundo de ultra contraste |
| **Fondo Sidebar** | `rgba(15, 23, 42, 0.95)` | Slate-900 con difuminado glassmorphism |
| **Botón Reindexar** | `#6366f1` a `#8b5cf6` | Gradiente violeta de alta visibilidad |
| **Conector Imports** | `#00f0ff` (Glow 8px) | Cyan fluorescente para importaciones |
| **Conector Calls** | `#a855f7` (Glow 8px) | Púrpura eléctrico para llamadas AST |
| **Conector Agente** | `#10b981` (Glow 10px) | Verde neón para canales del Harness |

---

## 6. Próximos Pasos de Implementación

1. Modificar `graphtyn/api/main.py` para incluir la estructura HTML5/CSS3 responsiva con Sidebar y Header Tabs.
2. Añadir el endpoint backend `@app.post("/api/reindex")` en la API FastAPI para re-escanear el repositorio determinista.
3. Integrar la visualización diferenciada de topología de agentes en la configuración de `3d-force-graph`.
