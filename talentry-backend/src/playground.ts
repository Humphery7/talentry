// import { PDFParse } from 'pdf-parse';


// const parser = new PDFParse({ url: 'Ufuoma_Otuoniyo_CV_Axpo.pdf' })

// const result = await parser.getText();
// console.log(result.text!)



import { pipeline } from '@huggingface/transformers';

const extractor = await pipeline('feature-extraction', 'Xenova/all-MiniLM-L6-v2')

async function generateEmbedding(text: string) {
    const output = await extractor(text, {
        pooling: "mean",
        normalize: true,
    });

    return Array.from(output.data);
}


console.log(await generateEmbedding("Hi i am trying again today"));