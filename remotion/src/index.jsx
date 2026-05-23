import React from 'react';
import {AbsoluteFill, Img, Sequence, interpolate, staticFile, useCurrentFrame} from 'remotion';
import {registerRoot, Composition, getInputProps} from 'remotion';

const DEFAULT_PROPS = {
  images: [],
  durationSeconds: 10,
  secondsPerImage: 5,
  width: 1920,
  height: 1080,
  fps: 30,
};

const imageSource = (path) => {
  if (path.includes(':/') || path.includes(':\\') || path.startsWith('/')) {
    return `file:///${path.replaceAll('\\', '/')}`;
  }

  return staticFile(path);
};

const TimelineImage = ({src, durationInFrames, index}) => {
  const frame = useCurrentFrame();
  const localFrame = frame;
  const progress = Math.max(0, Math.min(1, localFrame / Math.max(durationInFrames - 1, 1)));
  const zoom = interpolate(progress, [0, 1], [1.08, 1.28]);
  const rotate = interpolate(progress, [0, 1], [index % 2 === 0 ? -1.8 : 1.8, index % 2 === 0 ? 1.8 : -1.8]);
  const fadeFrames = Math.min(24, Math.floor(durationInFrames / 4));
  const fadeIn = interpolate(localFrame, [0, fadeFrames], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const fadeOut = interpolate(localFrame, [durationInFrames - fadeFrames, durationInFrames], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill style={{backgroundColor: 'black', opacity: Math.min(fadeIn, fadeOut)}}>
      <Img
        src={imageSource(src)}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          transform: `scale(${zoom}) rotate(${rotate}deg)`,
          filter: 'contrast(1.04) saturate(1.08)',
        }}
      />
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(circle at 50% 46%, rgba(255,255,255,0.06), rgba(0,0,0,0.32) 72%, rgba(0,0,0,0.5))',
        }}
      />
    </AbsoluteFill>
  );
};

const ImageTimeline = () => {
  const inputProps = getInputProps();
  const props = {...DEFAULT_PROPS, ...inputProps};
  const images = props.images.length > 0 ? props.images : [staticFile('placeholder.png')];
  const fps = props.fps;
  const secondsPerImage = props.secondsPerImage;
  const imageDuration = Math.max(1, Math.round(secondsPerImage * fps));

  return (
    <AbsoluteFill style={{backgroundColor: 'black'}}>
      {images.map((image, index) => {
        const startFrame = index * imageDuration;
        return (
          <Sequence key={`${image}-${index}`} from={startFrame} durationInFrames={imageDuration}>
            <TimelineImage src={image} durationInFrames={imageDuration} index={index} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

const RemotionRoot = () => {
  const inputProps = getInputProps();
  const props = {...DEFAULT_PROPS, ...inputProps};
  const fps = props.fps || DEFAULT_PROPS.fps;
  const durationInFrames = Math.max(1, Math.round((props.durationSeconds || DEFAULT_PROPS.durationSeconds) * fps));

  return (
    <Composition
      id="ImageTimeline"
      component={ImageTimeline}
      durationInFrames={durationInFrames}
      fps={fps}
      width={props.width || DEFAULT_PROPS.width}
      height={props.height || DEFAULT_PROPS.height}
      defaultProps={DEFAULT_PROPS}
    />
  );
};

registerRoot(RemotionRoot);
