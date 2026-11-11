#!/bin/zsh
# Cycle the lamp through every emotion so you can watch the animations in Blender.
f="${0:A:h}/emotion.txt"
for e in neutral happy laughing sad surprised neutral; do
  echo "$e"; echo "$e" > "$f"; sleep ${1:-6}
done
