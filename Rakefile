# Orchestration only: document logic lives in the Python package.
require 'json'
require 'time'

ROOT = File.expand_path(__dir__)

def cli(*arguments)
  sh 'uv', 'run', '--frozen', 'teify', *arguments
end

desc 'Install the uv environment and pinned TEI converter'
task :setup do
  sh 'uv', 'sync', '--frozen'
  sh 'bash', File.join(ROOT, 'scripts/setup-converter.sh')
end

desc 'Run the portable regression suite'
task :test do
  sh 'uv', 'run', '--frozen', 'pytest', '-m', 'not corpus', '-q'
end

desc 'Test representative local books; CORPUS points to their directory'
task :corpus do
  env = { 'TEIFY_REQUIRE_CORPUS' => '1', 'TEIFY_CORPUS' => ENV.fetch('CORPUS', File.join(ROOT, 'samples/selected')) }
  sh env, 'uv', 'run', '--frozen', 'pytest', '-m', 'corpus', '-q'
end

desc 'Convert and assert six representative books; retain TEI and reports in OUTPUT'
task :trial do
  output = File.expand_path(ENV.fetch('OUTPUT', File.join(ROOT, 'output/trials', Time.now.utc.strftime('%Y%m%dT%H%M%S%NZ'))))
  abort "Trial output already exists: #{output}; choose a new OUTPUT" if File.exist?(output)
  env = {
    'TEIFY_REQUIRE_CORPUS' => '1',
    'TEIFY_CORPUS' => ENV.fetch('CORPUS', File.join(ROOT, 'samples/selected')),
    'TEIFY_CORPUS_OUTPUT' => output
  }
  sh env, 'uv', 'run', '--frozen', 'pytest', '-m', 'corpus', '-v'
  puts "Verified TEI, figures, and reports: #{output}"
end

desc 'Audit an extracted corpus: INPUT=... OUTPUT=... JOBS=4; optional LIMIT'
task :batch do
  arguments = ['corpus', ENV.fetch('INPUT'), ENV.fetch('OUTPUT', 'output/corpus'), '--jobs', ENV.fetch('JOBS', '4')]
  arguments += ['--limit', ENV['LIMIT']] if ENV['LIMIT']
  arguments << '--retry-failed' if ENV['RETRY_FAILED'] == '1'
  cli(*arguments)
end

desc 'Convert one file or directory: INPUT=... OUTPUT=...'
task :convert do
  cli 'convert', ENV.fetch('INPUT'), ENV.fetch('OUTPUT', 'output/books')
end

desc 'Convert a growing archive: ARCHIVE=... OUTPUT=... JOBS=4; optional LIMIT'
task :archive do
  arguments = ['archive', ENV.fetch('ARCHIVE'), ENV.fetch('OUTPUT', 'output/archive'), '--jobs', ENV.fetch('JOBS', '4')]
  arguments << '--follow' unless ENV['FOLLOW'] == '0'
  arguments += ['--limit', ENV['LIMIT']] if ENV['LIMIT']
  cli(*arguments)
end

desc 'Show the latest archive-run status: OUTPUT=...'
task :status do
  path = File.join(ENV.fetch('OUTPUT', 'output/archive'), 'status.json')
  puts JSON.pretty_generate(JSON.parse(File.read(path)))
end

task default: :test
