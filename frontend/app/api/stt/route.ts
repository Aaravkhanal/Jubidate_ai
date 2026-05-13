import { NextRequest, NextResponse } from 'next/server';

export async function POST(req: NextRequest) {
  try {
    const { audioContent } = await req.json();

    if (!audioContent) {
      return NextResponse.json({ error: 'Audio content is required' }, { status: 400 });
    }

    const API_KEY = process.env.GOOGLE_API_KEY;
    if (!API_KEY) {
      return NextResponse.json({ error: 'Google API key is not configured' }, { status: 500 });
    }

    const response = await fetch(`https://speech.googleapis.com/v1/speech:recognize?key=${API_KEY}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        config: {
          encoding: 'WEBM_OPUS',
          sampleRateHertz: 48000,
          languageCode: 'en-US',
        },
        audio: {
          content: audioContent,
        },
      }),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(`Google STT API error: ${errorData.error?.message || response.statusText}`);
    }

    const data = await response.json();
    const transcript = data.results
      ?.map((result: any) => result.alternatives[0].transcript)
      .join('\n') || '';

    return NextResponse.json({ transcript });
  } catch (error) {
    console.error('Error in STT route:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
