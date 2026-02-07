import { create } from 'zustand';
import type { Project, Outline, Character, Chapter } from '../types';

interface AppState {
  currentProject: Project | null;
  setCurrentProject: (project: Project | null) => void;

  projects: Project[];
  setProjects: (projects: Project[]) => void;
  addProject: (project: Project) => void;
  updateProject: (id: string, project: Partial<Project>) => void;
  removeProject: (id: string) => void;

  outlines: Outline[];
  setOutlines: (outlines: Outline[]) => void;
  addOutline: (outline: Outline) => void;
  updateOutline: (id: string, outline: Partial<Outline>) => void;
  removeOutline: (id: string) => void;

  characters: Character[];
  setCharacters: (characters: Character[]) => void;
  addCharacter: (character: Character) => void;
  updateCharacter: (id: string, character: Partial<Character>) => void;
  removeCharacter: (id: string) => void;

  chapters: Chapter[];
  setChapters: (chapters: Chapter[]) => void;
  addChapter: (chapter: Chapter) => void;
  updateChapter: (id: string, chapter: Partial<Chapter>) => void;
  removeChapter: (id: string) => void;

  currentChapter: Chapter | null;
  setCurrentChapter: (chapter: Chapter | null) => void;

  loading: boolean;
  setLoading: (loading: boolean) => void;

  lastUpdated: {
    projects?: number;
    outlines?: number;
    characters?: number;
    chapters?: number;
  };
  markUpdated: (key: 'projects' | 'outlines' | 'characters' | 'chapters') => void;

  clearProjectData: () => void;
}

export const useStore = create<AppState>((set) => ({
  currentProject: null,
  setCurrentProject: (project) => set({ currentProject: project }),

  projects: [],
  setProjects: (projects) => set({ projects }),
  addProject: (project) => set((state) => ({ 
    projects: [...state.projects, project] 
  })),
  updateProject: (id, updatedProject) => set((state) => ({
    projects: state.projects.map((p) => 
      p.id === id ? { ...p, ...updatedProject } : p
    ),
    currentProject: state.currentProject?.id === id 
      ? { ...state.currentProject, ...updatedProject } 
      : state.currentProject,
  })),
  removeProject: (id) => set((state) => ({
    projects: state.projects.filter((p) => p.id !== id),
    currentProject: state.currentProject?.id === id ? null : state.currentProject,
  })),

  outlines: [],
  setOutlines: (outlines) => set({ outlines }),
  addOutline: (outline) => set((state) => ({ 
    outlines: [...state.outlines, outline] 
  })),
  updateOutline: (id, updatedOutline) => set((state) => ({
    outlines: state.outlines.map((o) => 
      o.id === id ? { ...o, ...updatedOutline } : o
    ),
  })),
  removeOutline: (id) => set((state) => ({
    outlines: state.outlines.filter((o) => o.id !== id),
  })),

  characters: [],
  setCharacters: (characters) => set({ characters }),
  addCharacter: (character) => set((state) => ({ 
    characters: [...state.characters, character] 
  })),
  updateCharacter: (id, updatedCharacter) => set((state) => ({
    characters: state.characters.map((c) => 
      c.id === id ? { ...c, ...updatedCharacter } : c
    ),
  })),
  removeCharacter: (id) => set((state) => ({
    characters: state.characters.filter((c) => c.id !== id),
  })),

  chapters: [],
  setChapters: (chapters) => set({ chapters }),
  addChapter: (chapter) => set((state) => ({ 
    chapters: [...state.chapters, chapter] 
  })),
  updateChapter: (id, updatedChapter) => set((state) => ({
    chapters: state.chapters.map((c) => 
      c.id === id ? { ...c, ...updatedChapter } : c
    ),
    currentChapter: state.currentChapter?.id === id 
      ? { ...state.currentChapter, ...updatedChapter } 
      : state.currentChapter,
  })),
  removeChapter: (id) => set((state) => ({
    chapters: state.chapters.filter((c) => c.id !== id),
    currentChapter: state.currentChapter?.id === id ? null : state.currentChapter,
  })),

  currentChapter: null,
  setCurrentChapter: (chapter) => set({ currentChapter: chapter }),

  loading: false,
  setLoading: (loading) => set({ loading }),

  lastUpdated: {},
  markUpdated: (key) => set((state) => ({
    lastUpdated: {
      ...state.lastUpdated,
      [key]: Date.now(),
    },
  })),

  clearProjectData: () => set({
    outlines: [],
    characters: [],
    chapters: [],
    currentChapter: null,
  }),
}));