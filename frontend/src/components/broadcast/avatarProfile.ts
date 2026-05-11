import type { Agent } from "@/types";

export type AvatarArchetype =
  | "prism-core"
  | "neural-mask"
  | "chrome-terminal"
  | "ink-strategist"
  | "waveform-face"
  | "carbon-visor"
  | "glass-lattice"
  | "signal-glyph";

export interface AgentVisualProfile {
  archetype: AvatarArchetype;
  label: string;
  roleLabel: string;
  primary: string;
  secondary: string;
  accent: string;
  glow: string;
  texture: string;
}

const ARCHETYPES: Array<{ id: AvatarArchetype; label: string }> = [
  { id: "prism-core", label: "Prism Core" },
  { id: "neural-mask", label: "Neural Mask" },
  { id: "chrome-terminal", label: "Chrome Terminal" },
  { id: "ink-strategist", label: "Ink Strategist" },
  { id: "waveform-face", label: "Waveform Face" },
  { id: "carbon-visor", label: "Carbon Visor" },
  { id: "glass-lattice", label: "Glass Lattice" },
  { id: "signal-glyph", label: "Signal Glyph" },
];

const PALETTES = [
  { primary: "#b9a7f2", secondary: "#17151f", accent: "#6df2c0", glow: "rgba(109, 242, 192, 0.34)" },
  { primary: "#b9e8f4", secondary: "#17252c", accent: "#f15c51", glow: "rgba(91, 181, 170, 0.36)" },
  { primary: "#f5ced6", secondary: "#24191d", accent: "#48a7f2", glow: "rgba(241, 92, 81, 0.28)" },
  { primary: "#ede2c7", secondary: "#15120d", accent: "#d79b46", glow: "rgba(230, 182, 87, 0.3)" },
  { primary: "#cfd4ff", secondary: "#181a2c", accent: "#25e6c8", glow: "rgba(37, 230, 200, 0.28)" },
  { primary: "#b7c0c7", secondary: "#101417", accent: "#f6d16d", glow: "rgba(246, 209, 109, 0.24)" },
  { primary: "#d8f0eb", secondary: "#13211f", accent: "#f07d5d", glow: "rgba(216, 240, 235, 0.24)" },
  { primary: "#d6bbe8", secondary: "#201625", accent: "#8be46d", glow: "rgba(139, 228, 109, 0.26)" },
];

function hashString(value: string) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash >>> 0);
}

export function getAgentVisualProfile(agent?: Agent, fallback = "host"): AgentVisualProfile {
  const key = agent?.model_id ?? agent?.portrait_seed ?? agent?.agent_id ?? agent?.pseudonym ?? fallback;
  const hash = hashString(key);
  const archetype = ARCHETYPES[hash % ARCHETYPES.length];
  const palette = PALETTES[Math.floor(hash / ARCHETYPES.length) % PALETTES.length];

  return {
    archetype: archetype.id,
    label: archetype.label,
    roleLabel: agent?.archetype ?? archetype.label,
    primary: palette.primary,
    secondary: palette.secondary,
    accent: palette.accent,
    glow: palette.glow,
    texture: `${(hash % 31) + 12}px`,
  };
}
