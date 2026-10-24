import type { FeatureExtractionPipeline } from '@huggingface/transformers';

// Produces 384-dimensional vectors; keep in sync with `vector(384)` in migrate.ts.
const MODEL = 'Xenova/all-MiniLM-L6-v2';

// The generic overload in transformers.js is too complex for TypeScript here.
type FeatureExtractorFactory = (
  task: 'feature-extraction',
  model: string,
  options: { dtype: 'fp32' },
) => Promise<FeatureExtractionPipeline>;

let extractorPromise: Promise<FeatureExtractionPipeline> | null = null;

function getExtractor(): Promise<FeatureExtractionPipeline> {
  if (!extractorPromise) {
    // Loaded only when an embedding is actually needed, not with the API.
    extractorPromise = import('@huggingface/transformers')
      .then(({ pipeline }) => {
        const createFeatureExtractor =
          pipeline as unknown as FeatureExtractorFactory;
        return createFeatureExtractor('feature-extraction', MODEL, {
          dtype: 'fp32',
        });
      })
      .catch((err) => {
        extractorPromise = null; // Let the next call retry after a transient failure.
        throw err;
      });
  }
  return extractorPromise;
}

/** Turns text into a normalized embedding vector. */
export async function createEmbedding(text: string): Promise<number[]> {
  const extractor = await getExtractor();
  const output = await extractor(text, {
    pooling: 'mean',
    normalize: true,
  });
  return Array.from(output.data);
}
