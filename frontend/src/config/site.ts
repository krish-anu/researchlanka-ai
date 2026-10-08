export type SiteProfile = "researchlanka" | "cse-uom";

export const SITE_PROFILE: SiteProfile =
  process.env.NEXT_PUBLIC_SITE_PROFILE === "cse-uom"
    ? "cse-uom"
    : "researchlanka";

export const IS_CSE_UOM_SITE = SITE_PROFILE === "cse-uom";

export const SITE_COPY = IS_CSE_UOM_SITE
  ? {
      shortName: "CSE Research",
      accentName: "Moratuwa",
      fullName: "CSE Research · University of Moratuwa",
      tagline: "AI RESEARCH, VERIFIED.",
      eyebrow: "University of Moratuwa · CSE research intelligence",
      metadataTitle: "UoM CSE — AI research analytics",
      metadataTemplate: "%s · UoM CSE Research",
      metadataDescription:
        "Publication analytics for affiliation-verified AI research from the University of Moratuwa Department of Computer Science and Engineering.",
      heroLead: "A clearer picture of",
      heroEmphasis: "AI research at UoM CSE.",
      heroDescription:
        "Explore the people, ideas, and collaborations shaping artificial intelligence research in the Department of Computer Science and Engineering.",
      scopeStrong: "UoM CSE AI publications only.",
      scopeBody:
        "Every record is linked to the official CSE staff roster and verified against University of Moratuwa affiliation evidence before AI classification.",
      compactScope: "Verified UoM CSE AI collection",
    }
  : {
      shortName: "Research",
      accentName: "Lanka",
      fullName: "ResearchLanka",
      tagline: "AI RESEARCH, CONNECTED.",
      eyebrow: "Sri Lanka · AI research intelligence",
      metadataTitle: "ResearchLanka — Sri Lanka AI research analytics",
      metadataTemplate: "%s · ResearchLanka",
      metadataDescription:
        "Public read-only analytics over the accepted Sri Lankan AI publication collection: national dashboards, publication search, researcher and institution profiles.",
      heroLead: "A clearer picture of",
      heroEmphasis: "AI research in Sri Lanka.",
      heroDescription:
        "Explore the people, ideas, and connections shaping artificial intelligence research — every figure is drawn from the accepted AI collection.",
      scopeStrong: "AI-related publications only.",
      scopeBody:
        "Charts, rankings, profiles, and exports describe the accepted AI collection.",
      compactScope: "AI collection only",
    };
