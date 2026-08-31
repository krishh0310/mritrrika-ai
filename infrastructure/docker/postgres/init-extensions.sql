-- Enable both extension families Mrittika AI depends on.
-- postgis      : parcel geometry, spatial queries, map bbox filtering (§11, §53)
-- vector       : semantic retrieval half of the RAG pipeline (§10)
-- pg_trgm      : fuzzy owner/village name search across transliterations (§17)
-- unaccent     : normalisation helper for search
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Fail loudly at container init if either critical extension is missing,
-- rather than surfacing as a confusing error mid-migration later.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis') THEN
        RAISE EXCEPTION 'postgis extension failed to install';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION 'pgvector extension failed to install';
    END IF;
    RAISE NOTICE 'Mrittika AI: postgis + pgvector ready';
END
$$;
